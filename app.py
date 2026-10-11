import datetime
import itertools
import sqlite3
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
    "Brooklyn Nets": "布魯克林網",
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
# 📡 數據解析：全盤口與白話說明
# -------------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_all_markets(api_key, sport_key):
    if not api_key:
        return None, "請設定 API Key！"

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return (
                None,
                f"API 連線失敗 (代碼 {response.status_code}): {response.text}",
            )
        data = response.json()
    except Exception as e:
        return None, f"連線異常: {str(e)}"

    if not data:
        return None, "目前沒有該賽事的即時盤口資料。"

    all_options = []

    for match in data:
        home_en = match.get("home_team", "")
        away_en = match.get("away_team", "")
        home_cn = TEAM_NAME_MAP.get(home_en, home_en)
        away_cn = TEAM_NAME_MAP.get(away_en, away_en)
        match_title = f"{home_cn} (主) vs {away_cn} (客)"

        if match.get("bookmakers"):
            bookmaker = match["bookmakers"][0]

            for market in bookmaker.get("markets", []):
                m_key = market["key"]

                # 1. 獨贏盤
                if m_key == "h2h":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(
                            outcome["name"], outcome["name"]
                        )
                        if outcome["name"] == "Draw":
                            pick_name = "和局"
                            p_win = 0.25
                        else:
                            is_home = outcome["name"] == home_en
                            pick_name = (
                                f"{team_cn} 不讓分勝"
                                f" ({'主場' if is_home else '客場'})"
                            )
                            p_win = 0.48 if is_home else 0.35

                        odds = outcome["price"]
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append(
                            {
                                "match": match_title,
                                "type": "不讓分 (獨贏)",
                                "pick": pick_name,
                                "detail": f"賠率 {odds}",
                                "odds": odds,
                                "win_prob": p_win,
                                "ev": ev,
                            }
                        )

                # 2. 讓分盤
                elif m_key == "spreads":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(
                            outcome["name"], outcome["name"]
                        )
                        point = outcome.get("point", 0)
                        point_str = f"+{point}" if point > 0 else str(point)
                        is_home = outcome["name"] == home_en
                        pick_name = (
                            f"{team_cn} 讓分 ({point_str})"
                            f" ({'主場' if is_home else '客場'})"
                        )

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append(
                            {
                                "match": match_title,
                                "type": "讓分盤",
                                "pick": pick_name,
                                "detail": f"盤口 ({point_str}) @ 賠率 {odds}",
                                "odds": odds,
                                "win_prob": p_win,
                                "ev": ev,
                            }
                        )

                # 3. 大小分
                elif m_key == "totals":
                    for outcome in market["outcomes"]:
                        name_cn = (
                            "大分"
                            if outcome["name"].lower() == "over"
                            else "小分"
                        )
                        point = outcome.get("point", 0)
                        pick_name = f"全場大小分：{name_cn} ({point} 球/分)"

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append(
                            {
                                "match": match_title,
                                "type": "大小分",
                                "pick": pick_name,
                                "detail": f"{point} {name_cn} @ 賠率 {odds}",
                                "odds": odds,
                                "win_prob": p_win,
                                "ev": ev,
                            }
                        )

    return pd.DataFrame(all_options), None


# -------------------------------------------------------------------
# 🚀 主程式頁面
# -------------------------------------------------------------------
if check_password("900812"):
    st.sidebar.success("✅ 權限驗證通過")
    if st.sidebar.button("🔒 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("⚡ ODD-HUNTER ｜ 賠率獵人 AI x 實體串關決策中心")
    st.caption(
        "全盤口動態選擇 ｜ 直白盤口細節標示 ｜ 擬真運彩串關投注單試算"
    )

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    # 1. 側邊欄控制項（確保變數優先宣告，解決 NameError）
    st.sidebar.header("⚙️ 選擇賽事與資金")
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

    budget = st.sidebar.number_input(
        "預計單張投注預算 ($)", min_value=10, value=100, step=10
    )

    if st.sidebar.button("🔄 手動刷新盤口數據"):
        st.cache_data.clear()
        st.rerun()

    # 2. 載入盤口資料
    with st.spinner("📡 正在抓取全盤口賠率數據中..."):
        df_all, error_msg = fetch_all_markets(api_key, selected_sport_key)

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        tab1, tab2 = st.tabs(
            ["📋 自由勾選盤口 (全玩法總覽)", "🎯 AI 智能精選推薦單"]
        )

        with tab1:
            st.subheader(f"🌐 {sport_choice} 全賽事盤口清單")
            st.info(
                "💡 **使用說明**：請在下方列表中直接勾選你想要串關的選項（可跨場次、跨玩法組合），下方會自動為你產出擬真彩券！"
            )

            matches = df_all["match"].unique()
            selected_items = []

            for m in matches:
                with st.expander(f"⚽/🏀 賽事：{m}", expanded=True):
                    sub_df = df_all[df_all["match"] == m]

                    c1, c2, c3 = st.columns(3)

                    with c1:
                        st.markdown("**【獨贏 / 不讓分】**")
                        for idx, row in sub_df[
                            sub_df["type"] == "不讓分 (獨贏)"
                        ].iterrows():
                            ev_color = "🟢" if row["ev"] > 0 else "⚪"
                            label = (
                                f"{row['pick']} | 賠率"
                                f" {row['odds']} ({ev_color} EV:"
                                f" {row['ev']})"
                            )
                            if st.checkbox(label, key=f"chk_{idx}"):
                                selected_items.append(row)

                    with c2:
                        st.markdown("**【讓分盤口】**")
                        for idx, row in sub_df[
                            sub_df["type"] == "讓分盤"
                        ].iterrows():
                            ev_color = "🟢" if row["ev"] > 0 else "⚪"
                            label = (
                                f"{row['pick']} | 賠率"
                                f" {row['odds']} ({ev_color} EV:"
                                f" {row['ev']})"
                            )
                            if st.checkbox(label, key=f"chk_{idx}"):
                                selected_items.append(row)

                    with c3:
                        st.markdown("**【大小分盤口】**")
                        for idx, row in sub_df[
                            sub_df["type"] == "大小分"
                        ].iterrows():
                            ev_color = "🟢" if row["ev"] > 0 else "⚪"
                            label = (
                                f"{row['pick']} | 賠率"
                                f" {row['odds']} ({ev_color} EV:"
                                f" {row['ev']})"
                            )
                            if st.checkbox(label, key=f"chk_{idx}"):
                                selected_items.append(row)

            # 擬真彩券購物車結算
            st.markdown("---")
            st.subheader("🧾 你的自選串關投注單")

            if len(selected_items) >= 1:
                total_odds = 1.0
                total_prob = 1.0

                st.write(f"已勾選 **{len(selected_items)}** 個投注選項：")

                for item in selected_items:
                    total_odds *= item["odds"]
                    total_prob *= item["win_prob"]
                    st.success(
                        f"📌 **{item['match']}** ➔ **{item['pick']}**"
                        f" （{item['detail']}）"
                    )

                total_odds = round(total_odds, 2)
                payout = round(budget * total_odds, 2)
                combo_ev = round((total_prob * total_odds) - 1, 3)

                st.markdown(
                    f"""
                <div style="background-color:#1e293b; padding:20px; border-radius:10px; border:2px solid #3b82f6;">
                    <h3 style="color:#60a5fa; margin-top:0;">🎟️ 串關彩券試算結果 ({len(selected_items)} 串 1)</h3>
                    <p style="font-size:18px;">💵 <b>投注預算</b>：$ {budget} 元</p>
                    <p style="font-size:18px;">⚡ <b>組合總賠率</b>：<span style="color:#f59e0b; font-size:22px; font-weight:bold;">{total_odds} 倍</span></p>
                    <p style="font-size:18px;">🎯 <b>預估全過過關率</b>：{total_prob:.1%}</p>
                    <p style="font-size:18px;">📈 <b>整體期望值 (EV)</b>：{combo_ev}</p>
                    <hr>
                    <h2 style="color:#10b981; margin-bottom:0;">💰 預計最高派彩金額：$ {payout} 元</h2>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            else:
                st.warning(
                    "💡 目前尚未勾選任何選項，請在上方賽事列表中勾選 1 個以上的投注項目！"
                )

        with tab2:
            st.subheader("🔥 AI 自動篩選高 EV 最佳買法推薦")

            positive_ev_df = df_all[df_all["ev"] > 0]

            if not positive_ev_df.empty:
                st.write("系統自動為你篩選出**期望值 > 0** 的最優質投注組合：")

                for match_name in positive_ev_df["match"].unique():
                    match_df = positive_ev_df[
                        positive_ev_df["match"] == match_name
                    ]

                    with st.container():
                        st.markdown(f"#### ⚽/🏀 {match_name}")
                        for _, r in match_df.iterrows():
                            st.info(
                                f"👉 **建議買法**：【**{r['pick']}**】\n"
                                f"* **盤口玩法**：{r['type']} |"
                                f" **細節**：`{r['detail']}`\n"
                                f"* **模型 EV (期望值)**：`+{r['ev']}` （具備長期投注價值）\n"
                                f"* **實戰下注指引**：開啟運彩投注 App ➔ 找到"
                                f" `{match_name}` ➔ 選擇"
                                f" `{r['type']}` ➔ 勾選"
                                f" **`{r['pick']}`**"
                            )
                        st.markdown("---")
            else:
                st.warning("目前實時盤口中暫無符合正期望值 (EV > 0) 的選項。")
