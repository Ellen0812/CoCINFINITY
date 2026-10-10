import itertools
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson
import streamlit as st

# -------------------------------------------------------------------
# 頁面基本設定
# -------------------------------------------------------------------
st.set_page_config(
    page_title="⚡ ODD-HUNTER ｜ 賠率獵人 AI x 實時數據分析",
    layout="wide",
)

TEAM_NAME_MAP = {
    # 足球 (EPL)
    "Arsenal": "阿仙奴",
    "Leeds United": "列斯聯",
    "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫",
    "Manchester United": "曼聯",
    "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦",
    "Manchester City": "曼城",
    # 籃球 (NBA)
    "Los Angeles Lakers": "洛杉磯湖人",
    "Golden State Warriors": "金州勇士",
    "Boston Celtics": "波士頓塞爾特人",
    "Miami Heat": "邁阿密熱火",
    "Brooklyn Nets": "布魯克林籃網",
    "Phoenix Suns": "菲尼克斯太陽",
}


# -------------------------------------------------------------------
# 🔒 密碼驗證模組
# -------------------------------------------------------------------
def check_password(target_password="900812"):
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 系統存取權限驗證")
        st.write("本系統為內部 AI 體育預測模型，請輸入授權密碼以繼續：")
        password_input = st.text_input("請輸入訪問密碼", type="password")

        if st.button("確認登入", use_container_width=True):
            if str(password_input) == str(target_password):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤！請重新輸入。")
    return False


# -------------------------------------------------------------------
# 📡 數據抓取與模型核心函數
# -------------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_and_analyze_data(api_key, sport_key, parlay_legs, min_odds_threshold):
    if not api_key:
        return None, "請設定 API Key！"

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return (
                None,
                f"API 連線失敗 (代碼 {response.status_code}):"
                f" {response.text}",
            )
        data = response.json()
    except Exception as e:
        return None, f"連線異常: {str(e)}"

    if not data:
        return None, "目前沒有該賽事的即時盤口資料。"

    analysis_list = []
    candidates_for_parlay = []

    for match in data:
        home_en = match.get("home_team", "")
        away_en = match.get("away_team", "")
        home_cn = TEAM_NAME_MAP.get(home_en, home_en)
        away_cn = TEAM_NAME_MAP.get(away_en, away_en)

        if match.get("bookmakers"):
            bookmaker = match["bookmakers"][0]

            h2h_market = next(
                (m for m in bookmaker["markets"] if m["key"] == "h2h"), None
            )
            home_odds, away_odds, draw_odds = None, None, None
            if h2h_market:
                for outcome in h2h_market["outcomes"]:
                    if outcome["name"] == home_en:
                        home_odds = outcome["price"]
                    elif outcome["name"] == away_en:
                        away_odds = outcome["price"]
                    elif outcome["name"] == "Draw":
                        draw_odds = outcome["price"]

            if "soccer" in sport_key:
                p_home, p_away = 0.48, 0.32
            else:
                p_home, p_away = 0.58, 0.42

            ev_home = round((p_home * home_odds) - 1, 3) if home_odds else -1
            ev_away = round((p_away * away_odds) - 1, 3) if away_odds else -1

            rec_option = "觀望"
            if ev_home > 0 and home_odds and home_odds >= min_odds_threshold:
                rec_option = f"主勝 ({home_cn})"
                candidates_for_parlay.append(
                    {
                        "match": f"{home_cn} vs {away_cn}",
                        "pick": f"{home_cn} 主勝",
                        "odds": home_odds,
                        "win_prob": p_home,
                    }
                )
            elif ev_away > 0 and away_odds and away_odds >= min_odds_threshold:
                rec_option = f"客勝 ({away_cn})"
                candidates_for_parlay.append(
                    {
                        "match": f"{home_cn} vs {away_cn}",
                        "pick": f"{away_cn} 客勝",
                        "odds": away_odds,
                        "win_prob": p_away,
                    }
                )

            analysis_list.append(
                {
                    "對陣": f"{home_cn} vs {away_cn}",
                    "主勝賠率": home_odds,
                    "和局賠率": draw_odds if draw_odds else "無",
                    "客勝賠率": away_odds,
                    "主勝 EV": ev_home,
                    "客勝 EV": ev_away,
                    "模型推薦": rec_option,
                }
            )

    df_analysis = pd.DataFrame(analysis_list)

    parlays = []
    if len(candidates_for_parlay) >= parlay_legs:
        for combo in itertools.combinations(
            candidates_for_parlay, parlay_legs
        ):
            t_odds = 1.0
            t_prob = 1.0
            combo_picks = []
            for item in combo:
                t_odds *= item["odds"]
                t_prob *= item["win_prob"]
                combo_picks.append(item["pick"])

            t_odds = round(t_odds, 2)
            parlays.append(
                {
                    "組合": " + ".join(combo_picks),
                    "總賠率": t_odds,
                    "預估全過機率": f"{t_prob:.1%}",
                    "組合 EV": round((t_prob * t_odds) - 1, 3),
                }
            )

    df_parlay = pd.DataFrame(parlays) if parlays else None
    return (df_analysis, df_parlay), None


# -------------------------------------------------------------------
# 🚀 主程式頁面
# -------------------------------------------------------------------
if check_password("900812"):
    st.sidebar.success("✅ 權限驗證通過")
    if st.sidebar.button("🔒 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("⚡ ODD-HUNTER ｜ 賠率獵人 AI x 實時數據分析")
    st.caption(
        "實時對接 The Odds API ｜ 多運動賽事與盤口 ｜ 靈活自訂過關策略"
    )

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    # 側邊欄控制項 (優先宣告控制變數)
    st.sidebar.header("⚙️ 賽事與策略選單")
    sport_choice = st.sidebar.selectbox(
        "選擇運動賽事",
        [
            "足球 - 英格蘭超級聯賽 (EPL)",
            "籃球 - 美國職業籃球 (NBA)",
        ],
    )

    sport_key_map = {
        "足球 - 英格蘭超級聯賽 (EPL)": "soccer_epl",
        "籃球 - 美國職業籃球 (NBA)": "basketball_nba",
    }
    selected_sport_key = sport_key_map[sport_choice]

    st.sidebar.subheader("🎯 串關策略設定")
    parlay_legs = st.sidebar.slider(
        "自訂過關關數 (串關數量)", min_value=2, max_value=4, value=2
    )
    min_odds_threshold = st.sidebar.number_input(
        "最低賠率過濾門檻", min_value=1.1, max_value=3.0, value=1.3, step=0.1
    )
    budget = st.sidebar.number_input(
        "預計投注預算 ($)", min_value=10, value=100, step=10
    )

    if st.sidebar.button("🔄 手動刷新實時盤口"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("📡 正在抓取最新實時賠率並計算期望值中..."):
        data_tuple, error_msg = fetch_and_analyze_data(
            api_key, selected_sport_key, parlay_legs, min_odds_threshold
        )

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        df_analysis, df_parlay = data_tuple

        tab1, tab2 = st.tabs(
            ["📊 實時盤口與 EV 分析表", f"🎯 AI 推薦 {parlay_legs} 串 1 組合"]
        )

        with tab1:
            st.subheader(f"🌐 {sport_choice} 賠率與 EV 演算")
            if df_analysis is not None and not df_analysis.empty:
                st.dataframe(df_analysis, use_container_width=True)
            else:
                st.info("目前無可供分析的賽事盤口數據。")

        with tab2:
            st.subheader(f"🔥 自動篩選：正 EV {parlay_legs} 串 1 過關單")
            if df_parlay is not None and not df_parlay.empty:
                for _, row in df_parlay.iterrows():
                    st.success(
                        f"### 🛡️ 推薦組合：{row['組合']}\n"
                        f"* **總賠率**：`{row['總賠率']} 倍` | **預估勝率**："
                        f" `{row['預估全過機率']}` | **EV**："
                        f" `{row['組合 EV']}`\n"
                        f"* **建議投注 $ {budget}** ➔ 預計最高派彩："
                        f" **$ {round(budget * row['總賠率'], 2)}**"
                    )
            else:
                st.warning(
                    f"目前盤口中無符合賠率 ≥ {min_odds_threshold} 且 EV > 0 的"
                    f" {parlay_legs} 串 1 組合條件。"
                )
