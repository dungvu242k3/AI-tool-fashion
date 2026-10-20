"""
Cấu hình chung cho tool nghiên cứu xu hướng sản phẩm.
"""

# ============================================================
# Danh mục & Niches
# ============================================================
CATEGORY = "Quà tặng theo mùa (Seasonal Gifts)"

NICHES = [
    {
        "name": "Christmas Gift Ideas",
        "seed_keywords": [
            "christmas gift ideas",
            "christmas gift ideas 2026",
            "best christmas gifts",
            "unique christmas gifts",
            "christmas gift for family",
        ],
        "subreddits": ["giftideas", "ChristmasGifts", "christmas", "gifts"],
        "amazon_search_terms": ["christmas gifts", "christmas gift ideas"],
    },
    {
        "name": "Gift for Him",
        "seed_keywords": [
            "gift for him",
            "gift ideas for men",
            "best gifts for boyfriend",
            "gifts for husband",
            "unique gifts for men 2026",
        ],
        "subreddits": ["giftideas", "gifts", "BuyItForLife", "malelifestyle"],
        "amazon_search_terms": ["gifts for him", "gifts for men"],
    },
    {
        "name": "Gift for Her",
        "seed_keywords": [
            "gift for her",
            "gift ideas for women",
            "best gifts for girlfriend",
            "gifts for wife",
            "unique gifts for women 2026",
        ],
        "subreddits": ["giftideas", "gifts", "TheGirlSurvivalGuide"],
        "amazon_search_terms": ["gifts for her", "gifts for women"],
    },
]

# ============================================================
# Ollama / LLM Config
# ============================================================
OLLAMA_BASE_URL = "http://localhost:11434"
# Model Qwen 2B verified on local machine:
OLLAMA_MODEL = "local-bench-qwen35-2b-q4km:latest"
# Alternative available model: "qwen2.5:3b-instruct-q4_K_M"
OLLAMA_TIMEOUT = 300  # seconds - cho model local đủ thời gian sinh text

# ============================================================
# Collector Config
# ============================================================
# Google Trends
GOOGLE_TRENDS_TIMEFRAME = "today 3-m"  # 3 tháng gần nhất
GOOGLE_TRENDS_GEO = ""  # Toàn cầu, đặt "US" nếu muốn focus US

# Amazon
AMAZON_BASE_URL = "https://www.amazon.com"
AMAZON_MAX_PRODUCTS = 20  # Số sản phẩm tối đa mỗi niche

# Reddit
REDDIT_MAX_POSTS = 15  # Số posts tối đa mỗi niche
REDDIT_TIME_FILTER = "month"  # hot posts trong 1 tháng gần nhất

# ============================================================
# Output
# ============================================================
REPORTS_DIR = "reports"
