# bot.py

import os
import sys
import discord
from discord.ext import commands
import sqlite3
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
import logging
import requests  # To fetch image bytes from URLs

# 2. Load environment vars
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 3. Ensure required environment variables are set
if not DISCORD_TOKEN:
    print("Error: DISCORD_TOKEN is not set in the environment variables.")
    sys.exit(1)
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY is not set in the environment variables.")
    sys.exit(1)

# 4. Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 5. Initialize Gen AI client (Gemini Developer API)
client = genai.Client(api_key=GEMINI_API_KEY)

DB_PATH = "foodbot.db"
DB_DIR = os.path.dirname(DB_PATH)

if DB_DIR and not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)


def create_tables():
    """
    Create the SQLite table 'meals' if it doesn't exist.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            image_url TEXT,
            description TEXT,
            classification_json TEXT
        )
    """)
    conn.commit()
    conn.close()


# Configure logging
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@bot.event
async def on_ready():
    create_tables()
    logger.info("Database tables created or verified.")
    logger.info(f"Bot logged in as {bot.user}")
    print(f"Bot logged in as {bot.user}")
    print(
        "Hello! I'm here to help you track your meals and stay healthy. "
        "Simply type or share a pic of your meal (in #food or via DM), and I'll classify it for you. "
        "You can also use the commands `!foodreport` or `!recommend` either in #food or via DM."
    )


@bot.event
async def on_message(message):
    logger.info(f"Received message from {message.author}: {message.content}")

    # Ignore messages from any bot (including ourselves).
    if message.author.bot:
        logger.info("Message ignored because it was sent by a bot.")
        return

    # Allow direct messages (DMs) or messages in "#food"
    if not isinstance(message.channel, discord.DMChannel):
        # If not a DM, it must be in #food
        if message.channel.name != "food":
            logger.info("Message ignored because it was not sent in the #food channel or via DM.")
            return

    # If the user typed "!foodreport" or "!recommend", defer to the command handler.
    cmd = message.content.strip().lower()
    if cmd.startswith("!foodreport") or cmd.startswith("!recommend"):
        logger.info("Message is a command. Passing to command handler.")
        await bot.process_commands(message)
        return

    # Check for image attachments
    image_url = None
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            image_url = attachment.url
            logger.info(f"Image attachment found: {image_url}")
            break  # Only use the first image found

    # Description text (if any)
    description_text = message.content.strip() or None

    # If no image and no text to log, ignore
    if not image_url and not description_text:
        logger.info("Message ignored because it contains no image or text.")
        return

    # Classify meal with Gemini (Gen AI SDK), showing a typing indicator
    logger.info("Classifying meal with Gemini.")
    try:
        async with message.channel.typing():
            classification = classify_meal_with_gemini(image_url, description_text)

            # --------------- New: If no description_text, infer food name from image ---------------
            if not description_text and image_url:
                try:
                    inferred_name = infer_food_name_from_image(image_url)
                    food_name = inferred_name
                except Exception as e:
                    logger.error(f"Error inferring food name: {e}")
                    food_name = "your meal"
            else:
                food_name = description_text or "your meal"

            # 1) Current meal breakdown (fractions)
            breakdown_lines = ["**📝 Current Meal Breakdown (fractions of weekly goals):**"]
            for grp, frac in classification.items():
                breakdown_lines.append(f"- **{grp.capitalize():<10}**: {frac:.2f}")

            # 2) Generate a personalized meal tip via Gemini, including the food name
            tip = generate_meal_tip(classification, food_name)

            # 3) Save classification to SQLite
            timestamp = datetime.utcnow().isoformat()
            conn = sqlite3.connect(DB_PATH)
            try:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO meals (user_id, timestamp, image_url, description, classification_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    str(message.author.id),
                    timestamp,
                    image_url,
                    description_text,
                    json.dumps(classification)
                ))
                conn.commit()
                logger.info("Meal successfully saved to the database.")
            except sqlite3.Error as e:
                logger.error(f"Error saving to database: {e}")
                await message.channel.send("😔 Sorry, I couldn't save your meal right now. Please try again later.")
                return
            finally:
                conn.close()

            # 4) Generate weekly progress report
            report = await generate_weekly_report(message.author.id)

        # Send the organized messages in sequence
        await message.channel.send("\n".join(breakdown_lines))
        await message.channel.send(f"💡 **Meal Tip:** {tip}")
        await message.channel.send(f"🍽️ **Weekly Progress:**\n{report}")

    except RuntimeError as e:
        logger.error(f"Gemini classification failed: {e}")
        await message.channel.send(
            f"😔 **Error:** Unable to classify your meal at the moment. Please try again later.\n**Details:** {e}"
        )
        return


@bot.command(name="foodreport")
async def food_report(ctx):
    # Show typing indicator while generating
    async with ctx.channel.typing():
        report = await generate_weekly_report(ctx.author.id)
    await ctx.send(f"🍽️ **Weekly Progress:**\n{report}")


@bot.command(name="recommend")
async def recommend(ctx):
    # Show typing while fetching recommendations
    async with ctx.channel.typing():
        response = await recommend_foods(ctx.author.id)
    await ctx.send(response)


def extract_json(raw_text: str) -> str:
    """
    Find the first '{' and last '}' and return only that substring.
    Raises ValueError if no valid JSON braces are found.
    """
    start = raw_text.find('{')
    end = raw_text.rfind('}')
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No valid JSON object found in response: {repr(raw_text)}")
    return raw_text[start:end + 1]


def classify_meal_with_gemini(image_url: str, text_description: str):
    """
    Sends an image URL and/or text description to the Gemini model via the Gen AI SDK.
    Returns a dict of { 'fruits': float, 'vegetables': float, ... } where each value
    is the fraction (0.0–1.0) of the WEEKLY recommended intake for that food group.
    Raises RuntimeError if the classification fails or the model does not return valid JSON.
    """

    # 0) Extensive instruction to force JSON‐only output with decimals representing fraction of weekly intake,
    #    including weekly recommended targets and nutritional highlights.
    json_schema_instruction = (
        "You are a classification assistant. Respond with valid JSON ONLY—no extra text or formatting.  "
        "Return exactly this structure: {\"fruits\": number, \"vegetables\": number, \"grains\": number, "
        "\"protein\": number, \"dairy\": number, \"oils\": number}.  "
        "Each value must be a decimal between 0.0 and 1.0 (inclusive), representing the fraction "
        "that this single meal contributes toward that food group's TOTAL WEEKLY recommended intake.  "
        "\n\n"
        "**Weekly Recommended Intake Guidelines:**\n"
        "1. Fruits:\n"
        "   • Adults should aim for 1.5 to 2 cups daily, totaling 10.5 to 14 cups weekly.\n"
        "   • Rich in fiber, vitamin C, potassium, and antioxidants.\n"
        "   • Include berries, citrus, melons, tropical fruits for diversity.\n\n"
        "2. Vegetables (14 to 21 cups weekly total):\n"
        "   • Dark-Green Vegetables: 1.5 cups/week (e.g., spinach, kale)\n"
        "   • Red & Orange Vegetables: 5.5 cups/week (e.g., carrots, tomatoes)\n"
        "   • Legumes (Beans & Peas): 1.5 cups/week\n"
        "   • Starchy Vegetables: 5 cups/week (e.g., potatoes, corn)\n"
        "   • Other Vegetables: 4 cups/week (e.g., onions, cucumbers)\n"
        "   • Provide fiber, folate, vitamins A & C, potassium, phytonutrients.\n\n"
        "3. Grains:\n"
        "   • 5 to 8 ounce-equivalents daily, totaling 35 to 56 ounces weekly.\n"
        "   • At least half should be whole grains (e.g., brown rice, whole wheat bread).\n"
        "   • Source of B vitamins, iron, magnesium, selenium, fiber.\n\n"
        "4. Protein Foods:\n"
        "   • 5 to 6.5 ounce-equivalents daily, 35 to 45.5 ounces weekly.\n"
        "     – Seafood: 8 ounces/week (e.g., salmon, tuna)\n"
        "     – Meats, Poultry, Eggs: 26 ounces/week\n"
        "     – Nuts, Seeds, Soy: 5 ounces/week\n"
        "     – Legumes (if not counted under vegetables)\n"
        "   • Provide essential amino acids, B vitamins, iron, zinc, omega-3s (from seafood).\n\n"
        "5. Dairy:\n"
        "   • 3 cups daily, totaling 21 cups weekly.\n"
        "   • Includes milk, yogurt, cheese, fortified soy beverages.\n"
        "   • Provide calcium, vitamin D, potassium, protein.\n\n"
        "6. Oils:\n"
        "   • Use in moderation; aim to include healthy oils (e.g., olive, canola) and nuts/seeds.\n\n"
        "For each food group, estimate how much of the weekly target this meal provides.  "
        "For example, if an average serving of mixed vegetables is 0.5 cup and the weekly target is 14 cups, "
        "then that serving is 0.5/14 ≈ 0.04.  Do NOT round prematurely; use at least two decimal places."
    )
    contents = [json_schema_instruction]

    # 1) Add the user’s description (if any)
    if text_description:
        contents.append(text_description)

    # 2) If there's an image URL, fetch its bytes and wrap as Part
    if image_url:
        try:
            resp = requests.get(image_url)
            resp.raise_for_status()
            mime_type = resp.headers.get("Content-Type", "image/jpeg")
            image_bytes = resp.content
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            contents.append(image_part)
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch image from URL: {e}")

    # 3) If no text or image besides the JSON instruction, return zeros
    if len(contents) == 1:
        return {grp: 0.0 for grp in ["fruits", "vegetables", "grains", "protein", "dairy", "oils"]}

    # 4) Call Gemini with the updated model name
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT"])
        )
    except Exception as e:
        raise RuntimeError(f"Error calling Gemini: {e}")

    raw_text = response.text or ""
    stripped = raw_text.strip()

    # 5) If the model returned nothing (or just whitespace), error out
    if not stripped:
        raise RuntimeError("Gemini returned an empty response for classification.")

    # 6) Extract only the JSON substring between the first '{' and last '}'.
    try:
        json_str = extract_json(stripped)
    except ValueError as e:
        logger.error(f"JSON extraction failed: {e}")
        raise RuntimeError(f"Unable to extract JSON from Gemini response; raw response:\n{repr(raw_text)}")

    # 7) Attempt to parse JSON and report errors clearly
    try:
        classification = json.loads(json_str)
    except json.JSONDecodeError:
        logger.error(f"Gemini responded with non‐JSON or malformed JSON:\n{repr(json_str)}")
        raise RuntimeError(f"Unable to parse JSON from Gemini; extracted response:\n{repr(json_str)}")

    # 8) Ensure all expected keys exist and convert to float
    result = {}
    for grp in ["fruits", "vegetables", "grains", "protein", "dairy", "oils"]:
        try:
            result[grp] = float(classification.get(grp, 0.0))
        except (TypeError, ValueError):
            result[grp] = 0.0

    return result


def infer_food_name_from_image(image_url: str) -> str:
    """
    Uses Gemini to generate a short description of the food in the image,
    returning a human-readable name (e.g., "kale salad" or "spaghetti").
    Raises RuntimeError if it cannot infer a name.
    """
    # Build a prompt to ask Gemini for a brief caption
    prompt_instruction = (
        "You are a food recognition assistant. Look at the attached image "
        "and provide a brief description of the main food item in one or two words. "
        "For example: 'kale salad', 'spaghetti', 'chicken sandwich'. "
        "If unsure, say 'a meal'."
    )
    contents = [prompt_instruction]

    # Fetch image bytes and wrap as Part
    try:
        resp = requests.get(image_url)
        resp.raise_for_status()
        mime_type = resp.headers.get("Content-Type", "image/jpeg")
        image_bytes = resp.content
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        contents.append(image_part)
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch image for inference: {e}")

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT"])
        )
        raw_text = response.text or ""
        return raw_text.strip()
    except Exception as e:
        raise RuntimeError(f"Error inferring food name: {e}")


def generate_meal_tip(classification: dict, food_name: str) -> str:
    """
    Given the classification fractions and the user-provided food_name,
    ask Gemini to build a friendly tip about this meal that names the food explicitly:
    1) Acknowledge what is good about the meal based on food_name and fractions,
    2) Mention the food_name in the message,
    3) Suggest a next step (e.g., drink water),
    4) Return plain, friendly advice (no JSON).
    """
    # Build a prompt that includes classification percentages, the food name, and clear instructions
    prompt = {
        "food_name": food_name,
        "classification": classification,
        "instructions": (
            "You are a helpful nutrition assistant. The user just logged a meal called \"{food_name}\" "
            "with the above food group fractions (where each fraction is the portion of that group's weekly target). "
            "Based on this, provide a short (1–2 sentence) tip that: "
            "1) Mentions the food_name explicitly and praises its healthy qualities (e.g., if vegetables fraction is high, praise that). "
            "2) Suggests a complementary action or food (e.g., drink water afterward). "
            "3) Does not include any JSON—just plain, friendly advice."
        ).replace("{food_name}", food_name)
    }

    contents = [json.dumps(prompt)]

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT"])
        )
        raw_tip = response.text or ""
        return raw_tip.strip()
    except Exception as e:
        logger.error(f"Error generating meal tip: {e}")
        return f"Enjoy your {food_name}! Stay hydrated and keep up the good choices."


async def recommend_foods(user_id: int):
    """
    Fetches all classification_json entries for the user, sums them to build a 'preferences' profile,
    and sends that profile to Gemini to receive food recommendations.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT classification_json FROM meals
            WHERE user_id = ?
        """, (str(user_id),))
        rows = c.fetchall()
    except sqlite3.Error as e:
        print(f"Error querying database: {e}")
        return "Sorry, I couldn't fetch your food preferences right now. Please try again later."
    finally:
        conn.close()

    preferences = {grp: 0.0 for grp in ["fruits", "vegetables", "grains", "protein", "dairy", "oils"]}
    for (json_str,) in rows:
        data = json.loads(json_str)
        for grp, frac in data.items():
            preferences[grp] += float(frac)

    prompt_obj = {
        "preferences": preferences,
        "instructions": (
            "You are a recommendation assistant. Respond with valid JSON ONLY—no extra text or formatting.  "
            "Return exactly this structure: { \"recommendations\": [\"food1\", \"food2\", …] }.  "
            "Based on the user's cumulative weekly food group intake fractions (each between 0.0 and 1.0), "
            "and considering the following weekly targets:\n"
            "• Fruits: 10.5–14 cups/week\n"
            "• Vegetables: 14–21 cups/week (dark-green 1.5, red/orange 5.5, legumes 1.5, starchy 5, other 4)\n"
            "• Grains: 35–56 ounces/week (≥50% whole grains)\n"
            "• Protein: 35–45.5 ounces/week (seafood 8, meats/poultry/eggs 26, nuts/seeds/soy 5)\n"
            "• Dairy: 21 cups/week\n"
            "• Oils: use healthy oils in moderation\n\n"
            "Suggest specific foods or meals that will help them meet or exceed 100% of each group's weekly goal.  "
            "Output only the JSON object."
        )
    }

    contents = [json.dumps(prompt_obj)]

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-8b",
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT"])
        )
    except Exception:
        return "Sorry, I couldn't fetch recommendations right now. Please try again later."

    raw_text = response.text or ""
    stripped = raw_text.strip()

    if not stripped:
        return "Sorry, Gemini returned no recommendations."

    # Extract only the JSON substring
    try:
        json_str = extract_json(stripped)
    except ValueError as e:
        logger.error(f"JSON extraction failed in recommend_foods: {e}")
        return "Sorry, I received an unexpected response format from Gemini."

    try:
        rec_data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.error(f"Gemini recommendations returned malformed JSON:\n{repr(json_str)}")
        return "Sorry, I received an unexpected response format from Gemini."

    recommendations = rec_data.get("recommendations", [])
    if recommendations:
        return "Here are some food recommendations for you: " + ", ".join(recommendations)
    else:
        return "I couldn't find any specific recommendations right now. Try eating a balanced meal!"


async def generate_weekly_report(user_id: int) -> str:
    logger.info(f"Generating weekly report for user {user_id}.")

    now = datetime.utcnow()
    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT classification_json FROM meals
        WHERE user_id = ? AND timestamp >= ?
    """, (str(user_id), start_of_week.isoformat()))
    rows = c.fetchall()
    conn.close()

    # Compute cumulative daily fractions for each group
    cumulative = {grp: 0.0 for grp in ["fruits", "vegetables", "grains", "protein", "dairy", "oils"]}
    for (json_str,) in rows:
        data = json.loads(json_str)
        for grp, frac in data.items():
            cumulative[grp] += float(frac)

    # Build the report header and compute percent of weekly
    report_lines = ["**📊 Weekly Food Intake Progress:**"]
    needs_ai_recommendation = False
    current_percentages = {}

    # Determine maximum length of capitalized group names for alignment
    max_group_length = max(len(grp.capitalize()) for grp in cumulative.keys())

    for grp, cum_daily_frac in cumulative.items():
        fraction_of_weekly = cum_daily_frac / 7.0
        if fraction_of_weekly > 1.0:
            fraction_of_weekly = 1.0
        percent = int(fraction_of_weekly * 100)
        current_percentages[grp] = percent

        filled = int(percent / 10)
        bar = "█" * filled + "░" * (10 - filled)
        # Left-align the group name within a fixed-width field
        padded_group = grp.capitalize().ljust(max_group_length)
        report_lines.append(f"- **{padded_group}**: [{bar}] {percent}% of weekly goal")

        if percent < 100:
            needs_ai_recommendation = True

    # If any group <100%, request AI‐based suggestions from Gemini
    ai_recs = {}
    if needs_ai_recommendation:
        logger.info("Requesting AI-based suggestions for incomplete goals.")
        ai_prompt = {
            "current_percentages": current_percentages,
            "instructions": (
                "Return valid JSON ONLY—no extra text.  "
                "Structure: { \"fruits\": \"single-sentence suggestion\", "
                "\"vegetables\": \"single-sentence suggestion\", … }.  "
                "For each food group below 100%, recommend a specific food or meal that will help achieve 100% "
                "of that week's goal.  Consider the weekly targets:\n"
                "• Fruits: 10.5–14 cups/week\n"
                "• Vegetables: 14–21 cups/week (dark-green 1.5, red/orange 5.5, legumes 1.5, starchy 5, other 4)\n"
                "• Grains: 35–56 ounces/week (≥50% whole grains)\n"
                "• Protein: 35–45.5 ounces/week (seafood 8, meats/poultry/eggs 26, nuts/seeds/soy 5)\n"
                "• Dairy: 21 cups/week\n"
                "• Oils: use healthy oils in moderation\n\n"
                "Output only the JSON object."
            )
        }

        contents = [json.dumps(ai_prompt)]

        try:
            ai_response = client.models.generate_content(
                model="gemini-1.5-flash-8b",
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["TEXT"])
            )
        except Exception:
            ai_recs = {}
        else:
            raw_ai = ai_response.text or ""
            stripped_ai = raw_ai.strip()
            if stripped_ai:
                try:
                    json_str = extract_json(stripped_ai)
                    ai_recs = json.loads(json_str)
                except Exception:
                    logger.error(f"AI recommendation parsing error: {repr(stripped_ai)}")
                    ai_recs = {}

    # Append AI suggestions or default text
    report_lines.append("\n**💡 Suggestions to Complete Weekly Targets:**")
    if ai_recs:
        for grp, suggestion in ai_recs.items():
            if grp in current_percentages and current_percentages[grp] < 100:
                report_lines.append(f"- **{grp.capitalize()}**: {suggestion}")
    else:
        for grp, percent in current_percentages.items():
            if percent < 100:
                if grp == "fruits":
                    report_lines.append(
                        f"- **Fruits{ ' ' * (max_group_length - len('Fruits')) }**: 🍓 Try adding a serving of berries or an apple."
                    )
                elif grp == "vegetables":
                    report_lines.append(
                        f"- **Vegetables**: 🥗 Consider a side salad with mixed greens."
                    )
                elif grp == "grains":
                    report_lines.append(
                        f"- **Grains{ ' ' * (max_group_length - len('Grains')) }**: 🍞 Have a slice of whole-grain toast or a bowl of oats."
                    )
                elif grp == "protein":
                    report_lines.append(
                        f"- **Protein{ ' ' * (max_group_length - len('Protein')) }**: 🍗 Grill a chicken breast or add beans to your meal."
                    )
                elif grp == "dairy":
                    report_lines.append(
                        f"- **Dairy{ ' ' * (max_group_length - len('Dairy')) }**: 🥛 Drink a cup of low-fat yogurt or milk."
                    )
                elif grp == "oils":
                    report_lines.append(
                        f"- **Oils{ ' ' * (max_group_length - len('Oils')) }**: 🥜 Cook with olive oil or snack on a handful of nuts."
                    )

    logger.info("Weekly report generated successfully.")
    return "\n".join(report_lines)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
