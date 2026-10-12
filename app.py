import datetime
import itertools
import sqlite3
import numpy as np
import pandas as pd
import requests
import streamlit as st

# -------------------------------------------------------------------
# 頁面基本設定
# -------------------------------------------------------------------
st.set_page_config(
    page_title="⚡ ODD-HUNTER ｜ 全球體育多模式決策中心",
    layout="wide",
)

TEAM_NAME_MAP = {
    # 足球 - 英超 (EPL)
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    "Newcastle United": "紐卡素", "West Ham United": "韋斯咸", "Fulham": "富咸",
    "Hull City": "侯城", "Ipswich Town": "葉士域治", "Brighton": "白禮頓",
    "Crystal Palace": "水晶宮", "Brentford": "賓福特", "Everton": "愛華頓",
    "Coventry City": "高雲地利",
    # 足球 - 西甲 (La Liga)
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",
    # 籃球 - NBA
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Boston Celtics": "波士頓塞爾特人", "Miami Heat": "邁阿密熱火",
    "Brooklyn Nets": "布魯克林網", "Phoenix Suns": "菲尼克斯太陽",
    # 棒球 - MLB
    "Los Angeles Dodgers": "洛杉磯道奇", "New York Yankees": "紐約洋基",
    "Atlanta Braves": "亞特蘭大勇士", "Houston Astros": "休士頓太空人",
}

SPORT_CATEGORIES = {
    "⚽ 足球 (Soccer)": {
        "英格蘭超級聯賽 (EPL)": "soccer_epl",
        "西班牙甲組聯賽 (La Liga)": "soccer_spain_la_liga",
        "義大利甲組聯賽 (Serie A)": "soccer_italy_serie_a",
        "德國甲組聯賽 (Bundesliga)": "soccer_germany_bundesliga",
        "歐洲冠軍聯賽 (UCL)": "soccer_uefa_champs_league",
    },
    "🏀 籃球 (Basketball)": {
        "美國職業籃球 (NBA)": "basketball_nba",
        "歐洲籃球聯賽 (EuroLeague)": "basketball_euroleague",
    },
    "⚾ 棒球 (Baseball)": {
        "美國職棒大聯盟 (MLB)": "baseball_mlb",
    },
    "🏒 冰球 (Ice Hockey)": {
        "北美冰球聯賽 (NHL)": "icehockey_nhl",
    },
    "🏈 美式足球 (NFL)": {
        "美國職業橄欖球聯賽 (NFL)": "americanfootball_nfl",
    },
}

ALL_MARKET_OPTIONS = ["不讓分 (獨贏)", "讓分盤", "大小分"]


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


@st.cache_data(ttl=600)
def fetch_all_markets(api_key, sport_key):
    if not api_key:
        return None, "請設定 API Key！"

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None, f"API 連線失敗 (代碼 {response.status_code}): {response.text}"
        data = response.json()
    except Exception as e:
        return None, f"連線異常: {str(e)}"

    if not data:
        return None, "目前該聯賽暫無即時開盤數據。"

    all_options = []

    for match in data:
        commence_utc = match.get("commence_time", "")
        if commence_utc:
            dt_utc = datetime.datetime.fromisoformat(commence_utc.replace("Z", "+00:00"))
            dt_local = dt_utc + datetime.timedelta(hours=8)
            time_str = dt_local.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = "時間未定"

        home_en = match.get("home_team", "")
        away_en = match.get("away_team", "")
        
        home_cn = TEAM_NAME_MAP.get(home_en, "")
        away_cn = TEAM_NAME_MAP.get(away_en, "")
        
        home_disp = f"{home_cn} {home_en}".strip()
        away_disp = f"{away_cn} {away_en}".strip()

        match_title = f"{home_disp} (主) vs {away_disp} (客)"

        if match.get("bookmakers"):
            bookmaker = match["bookmakers"][0]

            for market in bookmaker.get("markets", []):
                m_key = market["key"]

                if m_key == "h2h":
                    for outcome in market["outcomes"]:
                        team_en = outcome["name"]
                        team_cn = TEAM_NAME_MAP.get(team_en, team_en)
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        
                        if team_en == "Draw":
                            pick_name = "全場和局 (Draw)"
                        else:
                            is_home = team_en == home_en
                            pick_name = f"{team_cn} {team_en} 不讓分勝 ({'主' if is_home else '客'})"

                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "不讓分 (獨贏)",
                            "pick": pick_name,
                            "detail": f"賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                elif m_key == "spreads":
                    for outcome in market["outcomes"]:
                        team_en = outcome["name"]
                        team_cn = TEAM_NAME_MAP.get(team_en, team_en)
                        point = outcome.get("point", 0)
                        point_str = f"+{point}" if point > 0 else str(point)
                        pick_name = f"{team_cn} {team_en} 讓分 ({point_str})"
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "讓分盤",
                            "pick": pick_name,
                            "detail": f"盤口 ({point_str}) @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                elif m_key == "totals":
                    for outcome in market["outcomes"]:
                        name_en = outcome["name"]
                        name_cn = "大分 Over" if name_en.lower() == "over" else "小分 Under"
                        point = outcome.get("point", 0)
                        pick_name = f"全場大小分：{name_cn} ({point})"
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "大小分",
                            "pick": pick_name,
                            "detail": f"{point} {name_cn} @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

    return pd.DataFrame(all_options), None


# -------------------------------------------------------------------
# 🚀 主程式頁面
# -------------------------------------------------------------------
if check_password("900812"):
    st.sidebar.success("✅ 權限驗證通過")
    if st.sidebar.button("🔒 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("⚡ ODD-HUNTER ｜ 全球體育多模式決策中心")
    st.caption("單場直購 ｜ 純過關串關 ｜ 2 串 1 容錯組合 ｜ 動態切換")

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    st.sidebar.header("⚙️ 賽事與策略設定")
    selected_category = st.sidebar.selectbox("1. 選擇體育項目", list(SPORT_CATEGORIES.keys()))
    available_leagues = SPORT_CATEGORIES[selected_category]
    selected_league_name = st.sidebar.selectbox("2. 選擇特定聯賽", list(available_leagues.keys()))
    selected_sport_key = available_leagues[selected_league_name]

    bet_mode = st.sidebar.radio(
        "3. 選擇下注模式",
        ["🛡️ 系統 2 串 1 容錯組合 (推高勝率)", "🎟️ 純 N 串 1 過關 (追求高回報)", "🎯 單場投注 (不買串 / 獨立單)"]
    )

    user_selected_markets = st.sidebar.multiselect(
        "4. 選擇顯示玩法 (未選則全部顯示)",
        ALL_MARKET_OPTIONS,
        default=[]
    )

    display_markets = user_selected_markets if user_selected_markets else ALL_MARKET_OPTIONS

    budget = st.sidebar.number_input("總投注資金 ($)", min_value=10, value=100, step=10)

    if st.sidebar.button("🔄 刷新盤口數據"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner(f"📡 抓取 【{selected_league_name}】 數據中..."):
        df_all, error_msg = fetch_all_markets(api_key, selected_sport_key)

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        tab1, tab2 = st.tabs(["📋 自由勾選與注單計算", "🔥 AI 精選高勝率最穩組合"])

        with tab1:
            st.subheader(f"🌐 【{selected_league_name}】 即時賽事與盤口清單")
            st.caption(f"目前下注模式：**{bet_mode}**")

            if df_all is None or df_all.empty:
                st.warning("目前無即時開盤賽事。")
            else:
                matches = df_all["match"].unique()
                selected_items = []

                for m_idx, m in enumerate(matches):
                    sub_df = df_all[df_all["match"] == m]
                    m_time = sub_df["match_time"].iloc[0]

                    with st.expander(f"🏆 賽事：{m} ｜ ⏰ 開賽時間：{m_time}", expanded=True):
                        cols = st.columns(len(display_markets))

                        for col_idx, m_type in enumerate(display_markets):
                            with cols[col_idx]:
                                st.markdown(f"**【{m_type}】**")
                                type_df = sub_df[sub_df["type"] == m_type]

                                if type_df.empty:
                                    st.caption("無可提供盤口")
                                else:
                                    for idx, row in type_df.iterrows():
                                        chk_key = f"chk_{m_idx}_{col_idx}_{idx}"
                                        label = f"{row['pick']} | 賠率 {row['odds']} (勝率 {row['win_prob']:.0%})"
                                        if st.checkbox(label, key=chk_key):
                                            selected_items.append(row)

                st.markdown("---")
                st.subheader("🧾 你的自選投注單試算")

                if len(selected_items) >= 1:
                    st.write(f"已選擇 **{len(selected_items)}** 個選項：")
                    for item in selected_items:
                        st.success(
                            f"📌 **{item['match']}** (`{item['match_time']}`)\n"
                            f"➔ **{item['pick']}** （賠率 {item['odds']}）"
                        )

                    # 1. 🛡️ 容錯組合模式
                    if "容錯組合" in bet_mode:
                        if len(selected_items) >= 2:
                            combos_2 = list(itertools.combinations(selected_items, 2))
                            num_combos = len(combos_2)
                            unit_budget = round(budget / num_combos, 2)

                            st.markdown(f"""
                            <div style="background-color:#0f172a; padding:20px; border-radius:10px; border:2px solid #10b981;">
                                <h3 style="color:#10b981; margin-top:0;">🛡️ 高勝率「2 串 1 容錯組合」 ({num_combos} 組)</h3>
                                <p style="font-size:16px;">💵 <b>每組分配資金</b>：$ {unit_budget} 元 (總預算 $ {budget} 元)</p>
                                <p style="font-size:16px;">🎯 <b>過關優勢</b>：只要命中 2 場即開始派彩，錯 1 場仍可收彩！</p>
                            </div>
                            """, unsafe_allow_html=True)

                            st.write("▼ 拆解後的 2 串 1 子彩券明細：")
                            for c_idx, combo in enumerate(combos_2, 1):
                                c_odds = round(combo[0]['odds'] * combo[1]['odds'], 2)
                                c_payout = round(unit_budget * c_odds, 2)
                                st.info(
                                    f"**組合 #{c_idx}**：`{combo[0]['pick']}` + `{combo[1]['pick']}` "
                                    f"➔ **賠率 {c_odds} 倍** | 預計派彩：**$ {c_payout} 元**"
                                )
                        else:
                            st.warning("💡 容錯組合模式需要至少勾選 2 個以上的注單選項！")

                    # 2. 🎟️ 純 N 串 1 過關模式
                    elif "純 N 串 1" in bet_mode:
                        raw_odds = 1.0
                        raw_prob = 1.0
                        for item in selected_items:
                            raw_odds *= item['odds']
                            raw_prob *= item['win_prob']

                        raw_odds = round(raw_odds, 2)
                        payout = round(budget * raw_odds, 2)

                        st.markdown(f"""
                        <div style="background-color:#1e293b; padding:20px; border-radius:10px; border:2px solid #3b82f6;">
                            <h3 style="color:#60a5fa; margin-top:0;">🎟️ 純 {len(selected_items)} 串 1 彩券試算</h3>
                            <p style="font-size:16px;">💵 <b>總投注預算</b>：$ {budget} 元</p>
                            <p style="font-size:16px;">⚡ <b>串關總賠率</b>：<span style="color:#f59e0b; font-size:20px; font-weight:bold;">{raw_odds} 倍</span></p>
                            <p style="font-size:16px;">🎯 <b>預估全過過關率</b>：{raw_prob:.1%}</p>
                            <hr>
                            <h2 style="color:#10b981; margin-bottom:0;">💰 預計最高派彩：$ {payout} 元</h2>
                        </div>
                        """, unsafe_allow_html=True)

                    # 3. 🎯 單場投注模式 (不買串)
                    elif "單場投注" in bet_mode:
                        unit_budget = round(budget / len(selected_items), 2)
                        st.markdown(f"""
                        <div style="background-color:#1e1b4b; padding:20px; border-radius:10px; border:2px solid #818cf8;">
                            <h3 style="color:#a5b4fc; margin-top:0;">🎯 單場獨立投注試算 (共 {len(selected_items)} 場)</h3>
                            <p style="font-size:16px;">💵 <b>平注分配金額</b>：每場下注 $ {unit_budget} 元 (總預算 $ {budget} 元)</p>
                            <p style="font-size:16px;">🎯 <b>單場優勢</b>：互不影響，中哪場拿哪場，風險最低！</p>
                        </div>
                        """, unsafe_allow_html=True)

                        st.write("▼ 單場下注派彩明細：")
                        for s_idx, item in enumerate(selected_items, 1):
                            s_payout = round(unit_budget * item['odds'], 2)
                            st.info(
                                f"**單場 #{s_idx}**：`{item['match']}` ➔ `{item['pick']}` "
                                f"| 下注：**$ {unit_budget} 元** | 賠率：`{item['odds']}` | 命中派彩：**$ {s_payout} 元**"
                            )
                else:
                    st.warning("💡 請在上方賽事列表中勾選下注項目！")

        with tab2:
            st.subheader("🔥 AI 推薦：高勝率、低風險精選單")
            st.caption("優先篩選勝率高、賠率適中 (1.30 ~ 1.75) 的穩健選項")

            if df_all is not None and not df_all.empty:
                stable_df = df_all[(df_all['odds'] >= 1.30) & (df_all['odds'] <= 1.75)]
                
                if not stable_df.empty:
                    for match_name in stable_df['match'].unique():
                        m_df = stable_df[stable_df['match'] == match_name]
                        m_time = m_df["match_time"].iloc[0]

                        st.markdown(f"#### 🏆 {match_name} ｜ ⏰ 時間：{m_time}")
                        for _, r in m_df.iterrows():
                            st.success(
                                f"👉 **穩健推薦**：【**{r['pick']}**】\n"
                                f"* **賠率**：`{r['odds']}` | **勝率估計**：`{r['win_prob']:.1%}`\n"
                                f"* **開賽時間**：`{r['match_time']}`\n"
                                f"* **策略建議**：適合「單場獨立投注」或做為「2 串 1 容錯單」核心"
                            )
                else:
                    st.info("今日賽事無 1.30 ~ 1.75 賠率區間的穩健選項。")
