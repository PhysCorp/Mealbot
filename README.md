# 🍽️ Mealbot — A Discord Food Tracking Bot

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/Discord.py-2.0-blueviolet?logo=discord&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3.x-orange?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A **Discord bot** to help you log meals, track your weekly nutrition goals, and get AI-powered insights—all powered by **Google Gemini AI** and **SQLite**. Whether you drop an image or type a description, Mealbot breaks down your food groups, stores your data, and gives you personalized tips and recommendations. 🥗🍎

---

> ## 🔗 Invite the Bot!
> 
> Click [here](https://discord.com/oauth2/authorize?client_id=1379086226522509363&permissions=277025508352&scope=bot+applications.commands) to invite Mealbot to your server!
> 
---

## 🚀 Key Features

- **Meal Logging (Server & DM)**  
  • Upload an image or send a description of your meal in the `#food` channel _or_ DM the bot directly.  
  • Bot responds with a breakdown of how that meal contributes to your weekly nutrition goals (as decimal fractions).

- **AI-Powered Classification**  
  • Uses Google Gemini (“gemini-1.5-flash-8b”) to classify each meal into six food groups:  
    - Fruits  
    - Vegetables  
    - Grains  
    - Protein  
    - Dairy  
    - Oils  
  • Returns a JSON-only response indicating the fractional contribution toward each’s weekly target.

- **Personalized Meal Tip**  
  • After logging a meal, Mealbot crafts a short, friendly tip that:  
    1. Mentions the specific food you logged (e.g., “Given that you had spaghetti…”).  
    2. Praises healthy aspects (e.g., high vegetable content).  
    3. Suggests a complementary action (e.g., “Consider drinking water…”).  

- **Weekly Progress Report**  
  • Use `!foodreport` (in `#food` or via DM) to get a detailed, visual progress report.  
  • Progress bars indicate what percentage of each weekly goal you’ve achieved—aligned uniformly for readability.

- **Food Recommendations**  
  • Use `!recommend` to receive AI-generated suggestions on how to balance any incomplete food-group targets.  
  • Recommendations are delivered as a simple JSON array converted to a friendly message.

- **SQLite Database**  
  • All meal logs (timestamps, user ID, image URL, description, classification JSON) are stored locally in `foodbot.db`.  
  • Data persists across restarts, ensuring you never lose your progress.

---

## 📂 Project Structure

```
.
├── bot.py                 # Main bot logic (classification, tips, reports, commands)
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yaml    # Docker Compose setup
├── .env.bak               # Example environment variables
├── .gitignore             # Git ignore rules
└── README.md              # This documentation
```

---

> ## 🐳 Running with Docker
> 
> 1. **Build & Run**  
> ```bash
>    docker-compose up --build -d
> ```
> 
> This will:
> 
> * Build a Docker image named `mealbot`.
> * Launch the bot container in detached mode.
> 
> 2. **Stop the Bot**
> 
> ```bash
>    docker-compose down
> ```

---

## 🐳 Docker Setup (Development)

**Build Image**
```bash
docker build -t mealbot .
```

**Force Rebuild (no cache)**
```bash
docker build --no-cache -t mealbot .
```

---

## 💻 Local Setup (Development)

1. **Clone Repository**

   ```bash
   git clone https://github.com/PhysCorp/Mealbot.git
   cd Mealbot
   ```

2. **Environment Variables**
   Create a `.env` file in the project root:

   ```env
   DISCORD_TOKEN=your_discord_bot_token
   GEMINI_API_KEY=your_google_gemini_api_key
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run Locally**

   ```bash
   python bot.py
   ```

---

## 🔧 Available Commands

Use these commands either in the `#food` channel or via a Direct Message (DM) to the bot.

| Command       | Description                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------- |
| `!foodreport` | View your **weekly progress** across all food groups (with uniform progress bars).                |
| `!recommend`  | Get **AI-powered suggestions** on how to balance incomplete food-group targets (JSON → friendly). |

---

## 📝 How It Works

1. **Log a Meal**

   * **In `#food`:** Upload an image or type a description.
   * **Via DM:** Send a message with an image attachment or a text description.

2. **AI Classification & Tip**

   * Bot sends typing indicator, then:

     1. Breaks down “fractions of weekly goals” for each food group.
     2. Crafts a personalized tip that explicitly mentions your food (e.g., “Your kale salad is an excellent vegetable choice…”).
     3. Stores data in `foodbot.db`.

3. **Weekly Progress**

   * Use `!foodreport` to see progress bars for: Fruits, Vegetables, Grains, Protein, Dairy, Oils.
   * Progress bars are left-aligned for consistent display regardless of label length.

4. **Recommendations**

   * Use `!recommend` to receive a set of tailored food ideas to complete any incomplete group targets.

---

## 🌟 Example Interaction

```txt
User (in #food): Today I ate a bowl of kale salad
Bot (breakdown):
📝 Current Meal Breakdown (fractions of weekly goals):
- Fruits      : 0.00
- Vegetables  : 0.12
- Grains      : 0.00
- Protein     : 0.02
- Dairy       : 0.00
- Oils        : 0.01

Bot (tip):
💡 **Meal Tip:** Your kale salad is packed with vegetables and fiber—great job! Consider drinking a glass of water afterward to stay hydrated.

Bot (weekly progress):
🍽️ **Weekly Progress:**
- **Fruits     **: [░░░░░░░░░░] 0% of weekly goal
- **Vegetables **: [███░░░░░░░] 30% of weekly goal
- **Grains     **: [░░░░░░░░░░] 0% of weekly goal
- **Protein    **: [█░░░░░░░░░] 10% of weekly goal
- **Dairy      **: [░░░░░░░░░░] 0% of weekly goal
- **Oils       **: [░░░░░░░░░░] 0% of weekly goal
```

---

## 📦 Dependencies

* [discord.py](https://discordpy.readthedocs.io/)
* [python-dotenv](https://pypi.org/project/python-dotenv/)
* [google-genai](https://pypi.org/project/google-genai/)
* [requests](https://pypi.org/project/requests/)
* [SQLite3](https://www.sqlite.org/index.html) (bundled with Python)

---

## 🔐 Configuration & Secrets

Place a `.env` file in the project root with:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_google_gemini_api_key
```

> **Note:** Never commit your actual tokens or API keys to source control.

---

## 📝 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---
