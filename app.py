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
    page_title="⚡ ODD-HUNTER ｜ 雙欄即時決策 AI 體育中心",
    layout="wide",
    initial_sidebar_state="expanded"
)

TEAM_NAME_MAP = {
    # ⚾ 台灣職業棒球 (CPBL)
    "CTBC Brothers": "中信兄弟",
    "Brothers": "中信兄弟",
    "Uni-President Lions": "統一7-ELEVEn獅",
    "Uni-Lions": "統一7-ELEVEn獅",
    "Rakuten Monkeys": "樂天桃猿",
    "Monkeys": "樂天桃猿",
    "Fubon Guardians": "富邦悍將",
    "Guardians": "富邦悍將",
    "Wei Chuan Dragons": "味全龍",
    "Dragons": "味全龍",
    "TSG Hawks": "台鋼雄鷹",
    "Hawks": "台鋼雄鷹",

    # ⚽ 足球 - 英超 (EPL)
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    "Newcastle United": "紐卡素", "West Ham United": "韋斯咸", "Fulham": "富咸",
    "Hull City": "侯城", "Ipswich Town": "葉士域治", "Brighton": "白禮頓",
    "Crystal Palace": "水晶宮", "Brentford": "賓福特", "Everton": "愛華頓",
    "Coventry City": "高雲地利",

    # 🏀 籃球 - NBA
    "Detroit Pistons": "底特律活塞", "Boston Celtics": "波士頓塞爾特人",
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Miami Heat": "邁阿密熱火", "Brooklyn Nets": "布魯克林網", "Phoenix Suns": "菲尼克斯太陽",

    # ⚽ 足球 - 西甲 (La Liga)
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",

    # ⚾ 棒球 - MLB
    "Los Angeles Dodgers": "洛杉磯道奇", "New York Yankees": "紐約洋基",
    "Atlanta Braves": "亞特蘭大勇士", "Houston Astros": "休士頓太空人",
}

SPORT_CATEGORIES = {
    "⚾ 棒球 (Baseball)": {
        "台灣職業棒球 (CPBL)": "baseball_cpbl",
        "美國職棒大聯盟 (MLB)": "baseball_mlb",
    },
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
    "🏒 冰球 (Ice Hockey)": {
        "北美冰球聯賽 (NHL)": "icehockey_nhl",
    },
    "🏈 美式足球 (NFL)": {
        "美國職業橄欖球聯賽 (NFL)": "americanfootball_nfl",
    },
}

DEFAULT_MARKETS = ["不讓分 (獨贏)", "讓分盤", "大小分"]

SOCCER_MARKETS = [
    "全場三合一 (獨贏/讓分/大小)", "不讓分 (獨贏)", "讓分盤", "大小分",
    "雙重機會 (勝/和局 - 極高勝率)", "波膽 (正確比數)", "全場入球總數", "角球數賠率"
]

BASKETBALL_MARKETS = [
    "全場三合一 (獨贏/讓分/大小)", "不讓分 (獨贏)", "讓分盤", "大小分",
    "球隊取勝分差", "總得分單/雙數", "球隊得分上下盤 (大小)"
]

BASEBALL_MARKETS = [
    "不讓分 (獨贏)", "讓分盤", "大小分", "總得分單/雙數", "上半場 (前5局) 獨贏"
]


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
                    draw_odds = 3.5
                    for outcome in market["outcomes"]:
                        if outcome["name"] == "Draw":
                            draw_odds = outcome["price"]

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

                        if team_en != "Draw":
                            dc_odds = round(1 / ((1 / odds) + (1 / draw_odds)), 2)
                            dc_prob = round(1 / dc_odds, 4) if dc_odds > 0 else 0.8
                            all_options.append({
                                "match": match_title,
                                "match_time": time_str,
                                "type": "雙重機會 (勝/和局 - 極高勝率)",
                                "pick": f"🛡️ {team_cn} {team_en} 勝或和局 (Double Chance)",
                                "detail": f"賠率 {dc_odds}",
                                "odds": dc_odds,
                                "win_prob": dc_prob,
                                "ev": round((dc_prob * dc_odds) - 1, 3),
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
    if st.sidebar.button("🔒 登出系統", use_container_width=True):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("⚡ ODD-HUNTER ｜ 雙欄即時決策 AI 體育中心")
    st.caption("🛡️ 左側選單盤口 ｜ 📊 右側緊湊注單與過關率試算")

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    st.sidebar.header("⚙️ 賽事與策略設定")
    selected_category = st.sidebar.selectbox("1. 選擇體育項目", list(SPORT_CATEGORIES.keys()))
    available_leagues = SPORT_CATEGORIES[selected_category]
    selected_league_name = st.sidebar.selectbox("2. 選擇特定聯賽", list(available_leagues.keys()))
    selected_sport_key = available_leagues[selected_league_name]

    bet_mode = st.sidebar.radio(
        "3. 選擇下注模式",
        ["🎟️ 純 N 串 1 過關 (高賠率)", "🛡️ 系統 2 串 1 容錯組合 (穩健避險)", "🎯 單場獨立投注 (最高命中率)"]
    )

    min_win_prob = st.sidebar.slider(
        "4. 🎯 極致勝率門檻過濾 (%)",
        min_value=40,
        max_value=90,
        value=50,
        step=5
    )

    if "足球" in selected_category:
        available_market_list = SOCCER_MARKETS
    elif "籃球" in selected_category:
        available_market_list = BASKETBALL_MARKETS
    elif "棒球" in selected_category:
        available_market_list = BASEBALL_MARKETS
    else:
        available_market_list = DEFAULT_MARKETS

    user_selected_markets = st.sidebar.multiselect(
        "5. 選擇顯示玩法 (未選則預設全顯示)",
        available_market_list,
        default=[]
    )

    display_markets = user_selected_markets if user_selected_markets else DEFAULT_MARKETS
    budget = st.sidebar.number_input("總投注資金 ($)", min_value=10, value=100, step=10)

    if st.sidebar.button("🔄 刷新盤口數據", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    with st.spinner(f"📡 抓取 【{selected_league_name}】 數據中..."):
        df_all, error_msg = fetch_all_markets(api_key, selected_sport_key)

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        if df_all is not None and not df_all.empty:
            df_filtered = df_all[df_all['win_prob'] >= (min_win_prob / 100.0)]
        else:
            df_filtered = df_all

        tab1, tab2 = st.tabs(["📋 自由勾選與即時注單", "🔥 AI 精選極致高勝率單"])

        with tab1:
            left_col, right_col = st.columns([9, 3])

            selected_items = []

            # -------------------------------------------------------
            # 左欄：賽事清單與勾選區
            # -------------------------------------------------------
            with left_col:
                st.subheader(f"🌐 【{selected_league_name}】 盤口列表")
                st.caption(f"勝率門檻 $\ge {min_win_prob}\%$ ｜ 模式：**{bet_mode}**")

                if df_filtered is None or df_filtered.empty:
                    st.warning(f"目前無勝率 $\ge {min_win_prob}\%$ 的選項，請調整勝率門檻。")
                else:
                    matches = df_filtered["match"].unique()

                    for m_idx, m in enumerate(matches):
                        sub_df = df_filtered[df_filtered["match"] == m]
                        m_time = sub_df["match_time"].iloc[0]

                        with st.expander(f"🏆 {m}\n⏰ 開賽時間：{m_time}", expanded=True):
                            for col_idx, m_type in enumerate(display_markets):
                                if "三合一" in m_type:
                                    type_df = sub_df
                                else:
                                    type_df = sub_df[sub_df["type"] == m_type]

                                if not type_df.empty:
                                    st.markdown(f"**【{m_type}】**")
                                    for idx, row in type_df.iterrows():
                                        chk_key = f"chk_{m_idx}_{col_idx}_{idx}"
                                        label = f"{row['pick']} | 賠率 {row['odds']} (機率 {row['win_prob']:.0%})"
                                        if st.checkbox(label, key=chk_key):
                                            selected_items.append(row)
                                    st.markdown("---")

            # -------------------------------------------------------
            # 右欄：極致緊湊下注單面板
            # -------------------------------------------------------
            with right_col:
                st.subheader("🧾 投注單試算")

                if len(selected_items) >= 1:
                    st.caption(f"已選 **{len(selected_items)}** 項：")
                    for item in selected_items:
                        st.success(
                            f"📌 **{item['pick']}**\n"
                            f"賠率 `{item['odds']}` ｜ 機率 `{item['win_prob']:.0%}`"
                        )

                    st.markdown("---")

                    # 1. 🎟️ 純 N 串 1 過關模式
                    if "純 N 串 1" in bet_mode:
                        raw_odds = 1.0
                        raw_prob = 1.0
                        for item in selected_items:
                            raw_odds *= item['odds']
                            raw_prob *= item['win_prob']

                        raw_odds = round(raw_odds, 2)
                        payout = round(budget * raw_odds, 2)

                        st.markdown(f"""
                        <div style="background-color:#0f172a; padding:12px; border-radius:10px; border:2px solid #3b82f6;">
                            <h4 style="color:#60a5fa; margin-top:0; font-size:16px;">🎟️ 純 {len(selected_items)} 串 1 試算</h4>
                            <p style="font-size:13px; margin-bottom:4px;">💵 預算：<b>$ {budget}</b> 元</p>
                            <p style="font-size:13px; margin-bottom:4px;">⚡ 總賠率：<b style="color:#f59e0b;">{raw_odds} 倍</b></p>
                            <p style="font-size:13px; margin-bottom:8px;">🎯 機率：<b style="color:#ef4444;">{raw_prob:.1%}</b></p>
                            <hr style="border-color:#334155; margin:8px 0;">
                            <h3 style="color:#10b981; margin:0; font-size:18px;">💰 派彩：$ {payout}</h3>
                        </div>
                        """, unsafe_allow_html=True)

                    # 2. 🛡️ 容錯組合模式
                    elif "容錯組合" in bet_mode:
                        if len(selected_items) >= 2:
                            combos_2 = list(itertools.combinations(selected_items, 2))
                            num_combos = len(combos_2)
                            unit_budget = round(budget / num_combos, 2)

                            st.markdown(f"""
                            <div style="background-color:#0f172a; padding:12px; border-radius:10px; border:2px solid #10b981;">
                                <h4 style="color:#10b981; margin-top:0; font-size:16px;">🛡️ 2 串 1 ({num_combos} 組)</h4>
                                <p style="font-size:13px; margin-bottom:0;">💵 每組：<b>$ {unit_budget}</b> 元</p>
                            </div>
                            """, unsafe_allow_html=True)

                            st.caption("▼ 子彩券細節：")
                            for c_idx, combo in enumerate(combos_2, 1):
                                c_odds = round(combo[0]['odds'] * combo[1]['odds'], 2)
                                c_payout = round(unit_budget * c_odds, 2)
                                st.info(
                                    f"**#{c_idx}**：`{combo[0]['pick']}` + `{combo[1]['pick']}`\n"
                                    f"➔ `{c_odds}` 倍 ｜ 派彩：**$ {c_payout}**"
                                )
                        else:
                            st.warning("💡 請至少勾選 2 個選項！")

                    # 3. 🎯 單場獨立投注
                    elif "單場" in bet_mode:
                        unit_budget = round(budget / len(selected_items), 2)
                        st.markdown(f"""
                        <div style="background-color:#0f172a; padding:12px; border-radius:10px; border:2px solid #818cf8;">
                            <h4 style="color:#a5b4fc; margin-top:0; font-size:16px;">🎯 單場平注 ({len(selected_items)} 場)</h4>
                            <p style="font-size:13px; margin-bottom:0;">💵 每場：<b>$ {unit_budget}</b> 元</p>
                        </div>
                        """, unsafe_allow_html=True)

                        st.caption("▼ 單場細節：")
                        for s_idx, item in enumerate(selected_items, 1):
                            s_payout = round(unit_budget * item['odds'], 2)
                            st.info(
                                f"**#{s_idx}**：`{item['pick']}`\n"
                                f"➔ 賠率 `{item['odds']}` ｜ 派彩：**$ {s_payout}**"
                            )
                else:
                    st.info("👈 請在左側勾選賽事，右側將即時顯示試算！")

        with tab2:
            st.subheader("🔥 AI 精選：極致高勝率低風險單")
            st.caption("優先篩選估算勝率最高 (勝率 $\ge 70\%$) 的穩健避險項目")

            if df_all is not None and not df_all.empty:
                stable_df = df_all[df_all['win_prob'] >= 0.70]
                
                if not stable_df.empty:
                    for match_name in stable_df['match'].unique():
                        m_df = stable_df[stable_df['match'] == match_name]
                        m_time = m_df["match_time"].iloc[0]

                        st.markdown(f"#### 🏆 {match_name}\n⏰ 時間：{m_time}")
                        for _, r in m_df.iterrows():
                            st.success(
                                f"👉 **極高勝率推薦**：【**{r['pick']}**】\n"
                                f"* **賠率**：`{r['odds']}` | **估計勝率**：`<span style='color:#10b981; font-weight:bold;'>{r['win_prob']:.1%}</span>`\n"
                                f"* **開賽時間**：`{r['match_time']}`\n"
                                f"* **策略建議**：勝率 $\ge 70\%$，極推薦採用「單場平注」下注以保持最高勝率！"
                            )
                else:
                    st.info("今日賽事暫無勝率 $\ge 70\%$ 的超高勝率選項。")
