import datetime as dt
import itertools
from collections import defaultdict

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="⚡ ODD-HUNTER ｜ 雙欄即時決策 AI 體育中心",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# 常數
# ------------------------------------------------------------------
TEAM_NAME_MAP = {
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    "Newcastle United": "紐卡素", "West Ham United": "韋斯咸", "Fulham": "富咸",
    "Hull City": "侯城", "Ipswich Town": "葉士域治", "Brighton": "白禮頓",
    "Crystal Palace": "水晶宮", "Brentford": "賓福特", "Everton": "愛華頓",
    "Coventry City": "高雲地利", "Detroit Pistons": "底特律活塞",
    "Boston Celtics": "波士頓塞爾特人", "Real Madrid": "皇家馬德里",
    "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Miami Heat": "邁阿密熱火", "Brooklyn Nets": "布魯克林網",
    "Phoenix Suns": "菲尼克斯太陽", "Los Angeles Dodgers": "洛杉磯道奇",
    "New York Yankees": "紐約洋基", "Atlanta Braves": "亞特蘭大勇士",
    "Houston Astros": "休士頓太空人",
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
    "⚾ 棒球 (Baseball)": {"美國職棒大聯盟 (MLB)": "baseball_mlb"},
    "🏒 冰球 (Ice Hockey)": {"北美冰球聯賽 (NHL)": "icehockey_nhl"},
    "🏈 美式足球 (NFL)": {"美國職業橄欖球聯賽 (NFL)": "americanfootball_nfl"},
}

# 注意:原本列出但沒有資料來源的玩法(波膽、角球等)已移除,
# 否則選了也只會顯示空白。
DEFAULT_MARKETS = ["不讓分 (獨贏)", "讓分盤", "大小分"]
SOCCER_MARKETS = DEFAULT_MARKETS + ["雙重機會 (勝/和局)"]
MARKETS_BY_CATEGORY = {"足球": SOCCER_MARKETS}

TZ_LOCAL = dt.timezone(dt.timedelta(hours=8))


# ------------------------------------------------------------------
# 登入(密碼放 .streamlit/secrets.toml)
# ------------------------------------------------------------------
def check_password() -> bool:
    if st.session_state.get("password_correct"):
        return True

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("🔒 系統存取權限驗證")
        pwd = st.text_input("請輸入訪問密碼", type="password")
        if st.button("確認登入", use_container_width=True):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤！請重新輸入。")
    return False


# ------------------------------------------------------------------
# 資料處理
# ------------------------------------------------------------------
def devig(prices: list[float]) -> list[float]:
    """把含抽水的隱含機率正規化成總和為 1 的公平機率。"""
    inv = [1 / p for p in prices]
    total = sum(inv)
    return [x / total for x in inv]


def fmt_time(iso: str) -> str:
    if not iso:
        return "時間未定"
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return t.astimezone(TZ_LOCAL).strftime("%Y-%m-%d %H:%M")


def cn(name: str) -> str:
    c = TEAM_NAME_MAP.get(name, "")
    return f"{c} {name}".strip()


def consensus(match: dict, mkey: str):
    """
    回傳 {(name, point): {"prob": 各莊家去水後平均機率, "best": 最佳賠率}}
    """
    probs, best = defaultdict(list), {}
    for bk in match.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] != mkey:
                continue
            outs = mk["outcomes"]
            if any(o["price"] <= 1 for o in outs):
                continue
            fair = devig([o["price"] for o in outs])
            for o, p in zip(outs, fair):
                k = (o["name"], o.get("point"))
                probs[k].append(p)
                best[k] = max(best.get(k, 0), o["price"])
    return {
        k: {"prob": sum(v) / len(v), "best": best[k]} for k, v in probs.items()
    }


def make_row(mid, title, time_str, mtype, pick, odds, prob):
    return {
        "id": f"{mid}|{mtype}|{pick}",
        "match_id": mid,
        "match": title,
        "match_time": time_str,
        "type": mtype,
        "pick": pick,
        "odds": round(odds, 2),
        "win_prob": round(prob, 4),
        "ev": round(prob * odds - 1, 3),   # 共識機率 × 最佳賠率,才有參考價值
    }


@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_markets(api_key: str, sport_key: str):
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
            params={
                "apiKey": api_key, "regions": "eu",
                "markets": "h2h,spreads,totals", "oddsFormat": "decimal",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except requests.HTTPError as e:
        return None, f"API 連線失敗 (代碼 {e.response.status_code})"
    except requests.RequestException as e:
        return None, f"連線異常: {type(e).__name__}"

    if not data:
        return None, "目前該聯賽暫無即時開盤數據。"

    rows = []
    for m in data:
        mid = m["id"]
        home, away = m.get("home_team", ""), m.get("away_team", "")
        title = f"{cn(home)} (主) vs {cn(away)} (客)"
        t = fmt_time(m.get("commence_time", ""))
        add = lambda *a: rows.append(make_row(mid, title, t, *a))

        # 不讓分 + 雙重機會
        h2h = consensus(m, "h2h")
        draw = h2h.get(("Draw", None))
        for (name, _), v in h2h.items():
            if name == "Draw":
                add("不讓分 (獨贏)", "全場和局 (Draw)", v["best"], v["prob"])
                continue
            side = "主" if name == home else "客"
            add("不讓分 (獨贏)", f"{cn(name)} 不讓分勝 ({side})", v["best"], v["prob"])
            if draw:
                p_dc = v["prob"] + draw["prob"]
                # 雙重機會賠率:公平機率 × 約 5% 抽水的保守估計
                add("雙重機會 (勝/和局)", f"🛡️ {cn(name)} 勝或和局",
                    0.95 / p_dc, p_dc)

        # 讓分
        for (name, pt), v in consensus(m, "spreads").items():
            pt = pt or 0
            add("讓分盤", f"{cn(name)} 讓分 ({pt:+g})", v["best"], v["prob"])

        # 大小分
        for (name, pt), v in consensus(m, "totals").items():
            label = "大分 Over" if name.lower() == "over" else "小分 Under"
            add("大小分", f"全場大小分：{label} ({pt})", v["best"], v["prob"])

    return pd.DataFrame(rows), None


# ------------------------------------------------------------------
# 試算
# ------------------------------------------------------------------
def card(color, title_color, title, body):
    st.markdown(
        f"""<div style="background:#0f172a;padding:18px;border-radius:12px;
        border:2px solid {color};"><h3 style="color:{title_color};margin-top:0;
        font-size:20px;">{title}</h3>{body}</div>""",
        unsafe_allow_html=True,
    )


def render_betslip(items, bet_mode, budget):
    st.write(f"已選擇 **{len(items)}** 個選項：")
    for it in items:
        st.success(
            f"📌 **{it['match']}** (`{it['match_time']}`)\n"
            f"➔ **{it['pick']}** (賠率 {it['odds']} | 機率 {it['win_prob']:.0%})"
        )
    st.markdown("---")

    if "純 N 串 1" in bet_mode:
        if len({it["match_id"] for it in items}) < len(items):
            st.warning("⚠️ 同一場比賽的選項彼此相關,多數莊家不允許串在一起。")
        odds = prob = 1.0
        for it in items:
            odds *= it["odds"]
            prob *= it["win_prob"]
        card("#3b82f6", "#60a5fa", f"🎟️ 純 {len(items)} 串 1 試算", f"""
            <p>💵 總投注：$ {budget}</p>
            <p>⚡ 總賠率：<b style="color:#f59e0b">{odds:.2f} 倍</b></p>
            <p>🎯 估算全過機率：<b style="color:#ef4444">{prob:.1%}</b></p>
            <hr style="border-color:#334155">
            <h2 style="color:#10b981;margin:0">💰 最高派彩：$ {budget * odds:,.2f}</h2>""")

    elif "容錯組合" in bet_mode:
        if len(items) < 2:
            st.warning("💡 容錯組合模式需要至少勾選 2 個選項！")
            return
        combos = list(itertools.combinations(items, 2))
        unit = budget / len(combos)
        card("#10b981", "#10b981", f"🛡️ 2 串 1 組合 ({len(combos)} 組)",
             f"<p>💵 每組 $ {unit:.2f}(總預算 $ {budget})</p>")
        for i, (a, b) in enumerate(combos, 1):
            o, p = a["odds"] * b["odds"], a["win_prob"] * b["win_prob"]
            st.info(f"**組合 #{i}**：`{a['pick']}` + `{b['pick']}`\n"
                    f"➔ 賠率 {o:.2f} | 過關率 {p:.1%} | 派彩 $ {unit * o:,.2f}")

    else:
        unit = budget / len(items)
        card("#818cf8", "#a5b4fc", f"🎯 單場獨立投注 (共 {len(items)} 場)",
             f"<p>💵 每場 $ {unit:.2f}(總預算 $ {budget})</p>")
        for i, it in enumerate(items, 1):
            st.info(f"**單場 #{i}**：`{it['match']}`\n"
                    f"➔ `{it['pick']}` | 機率 {it['win_prob']:.0%} | "
                    f"賠率 {it['odds']} | 派彩 $ {unit * it['odds']:,.2f}")


# ------------------------------------------------------------------
# 主程式
# ------------------------------------------------------------------
if not check_password():
    st.stop()

st.sidebar.success("✅ 權限驗證通過")
if st.sidebar.button("🔒 登出系統", use_container_width=True):
    st.session_state["password_correct"] = False
    st.rerun()

st.title("⚡ ODD-HUNTER ｜ 雙欄即時決策 AI 體育中心")
st.caption("🛡️ 左側選單盤口 ｜ 📊 右側即時注單與過關率試算")

st.sidebar.header("⚙️ 賽事與策略設定")
category = st.sidebar.selectbox("1. 選擇體育項目", list(SPORT_CATEGORIES))
leagues = SPORT_CATEGORIES[category]
league_name = st.sidebar.selectbox("2. 選擇特定聯賽", list(leagues))
sport_key = leagues[league_name]

bet_mode = st.sidebar.radio("3. 選擇下注模式", [
    "🎟️ 純 N 串 1 過關 (高賠率)",
    "🛡️ 系統 2 串 1 容錯組合 (穩健避險)",
    "🎯 單場獨立投注 (最高命中率)",
])
min_prob = st.sidebar.slider("4. 🎯 機率門檻過濾 (%)", 40, 90, 50, 5)

market_options = next(
    (v for k, v in MARKETS_BY_CATEGORY.items() if k in category), DEFAULT_MARKETS
)
chosen = st.sidebar.multiselect("5. 選擇顯示玩法 (未選則全顯示)", market_options)
display_markets = chosen or market_options
budget = st.sidebar.number_input("總投注資金 ($)", min_value=10, value=100, step=10)

if st.sidebar.button("🔄 刷新盤口數據", use_container_width=True):
    fetch_all_markets.clear()      # 只清這個函式的快取
    st.rerun()

with st.spinner(f"📡 抓取 【{league_name}】 數據中..."):
    df_all, err = fetch_all_markets(st.secrets["ODDS_API_KEY"], sport_key)

if err:
    st.error(f"❌ 數據載入失敗：{err}")
    st.stop()

df = df_all[
    df_all["win_prob"].ge(min_prob / 100) & df_all["type"].isin(display_markets)
]

tab1, tab2 = st.tabs(["📋 自由勾選與即時注單", "🔥 高機率選項"])

with tab1:
    left, right = st.columns([7, 5])
    selected = []

    with left:
        st.subheader(f"🌐 【{league_name}】 盤口列表")
        st.caption(f"機率門檻 ≥ {min_prob}% ｜ 模式：**{bet_mode}**")

        if df.empty:
            st.warning(f"目前無機率 ≥ {min_prob}% 的選項,請調整門檻。")
        else:
            for _, m_df in df.groupby("match_id", sort=False):
                first = m_df.iloc[0]
                with st.expander(f"🏆 {first['match']}\n⏰ 開賽時間：{first['match_time']}",
                                 expanded=True):
                    for m_type, t_df in m_df.groupby("type", sort=False):
                        st.markdown(f"**【{m_type}】**")
                        for row in t_df.to_dict("records"):
                            label = (f"{row['pick']} | 賠率 {row['odds']} "
                                     f"(機率 {row['win_prob']:.0%})")
                            if st.checkbox(label, key=f"chk_{row['id']}"):
                                selected.append(row)
                        st.markdown("---")

    with right:
        st.subheader("🧾 你的自選投注單試算")
        if selected:
            render_betslip(selected, bet_mode, budget)
        else:
            st.info("👈 請在左側勾選比賽,右側將即時試算。")

with tab2:
    st.subheader("🔥 高機率選項(機率 ≥ 70%)")
    st.caption("機率為多家莊家去水後的共識機率。高機率不等於高價值:賠率通常很低。")
    top = df_all[df_all["win_prob"] >= 0.70]
    if top.empty:
        st.info("目前暫無機率 ≥ 70% 的選項。")
    else:
        for _, m_df in top.groupby("match_id", sort=False):
            first = m_df.iloc[0]
            st.markdown(f"#### 🏆 {first['match']}\n⏰ {first['match_time']}")
            for r in m_df.to_dict("records"):
                st.success(f"👉 **{r['pick']}**\n\n賠率 `{r['odds']}` ｜ "
                           f"共識機率 `{r['win_prob']:.1%}` ｜ EV `{r['ev']:+.3f}`")
