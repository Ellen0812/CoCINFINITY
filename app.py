import datetime as dt
import itertools
import math
import os
from collections import defaultdict
from math import prod

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="⚡ ODD-HUNTER ｜ 複式組合 AI 體育決策中心", layout="wide")

# 全域購物車暫存 (跨聯賽混合選擇)
if "cart" not in st.session_state:
    st.session_state.cart = {}

TEAMS = dict(p.split("=") for p in """Arsenal=阿仙奴;Leeds United=列斯聯;Chelsea=車路士;
Bournemouth=般尼茅夫;Manchester United=曼聯;Tottenham Hotspur=熱刺;Liverpool=利物浦;
Manchester City=曼城;Aston Villa=阿士東維拉;Newcastle United=紐卡素;West Ham United=韋斯咸;
Fulham=富咸;Hull City=侯城;Ipswich Town=葉士域治;Brighton=白禮頓;Crystal Palace=水晶宮;
Brentford=賓福特;Everton=愛華頓;Coventry City=高雲地利;Detroit Pistons=底特律活塞;
Boston Celtics=波士頓塞爾特人;Real Madrid=皇家馬德里;Barcelona=巴塞隆拿;
Atletico Madrid=馬德里體育會;Los Angeles Lakers=洛杉磯湖人;Golden State Warriors=金州勇士;
Miami Heat=邁阿密熱火;Brooklyn Nets=布魯克林網;Phoenix Suns=菲尼克斯太陽;
Los Angeles Dodgers=洛杉磯道奇;New York Yankees=紐約洋基;Atlanta Braves=亞特蘭大勇士;
Houston Astros=休士頓太空人;
Uni-President 7-Eleven Lions=統一7-ELEVEn獅;CTBC Brothers=中信兄弟;
Rakuten Monkeys=樂天桃猿;Fubon Guardians=富邦悍將;Wei Chuan Dragons=味全龍;
TSG Hawks=台鋼雄鷹""".replace("\n", "").split(";"))

LEAGUES = {
    "⚽ 足球": {"英超 EPL": "soccer_epl", "西甲": "soccer_spain_la_liga",
              "意甲": "soccer_italy_serie_a", "德甲": "soccer_germany_bundesliga",
              "歐冠": "soccer_uefa_champs_league"},
    "🏀 籃球": {"NBA": "basketball_nba", "歐洲聯賽": "basketball_euroleague"},
    "⚾ 棒球": {"MLB": "baseball_mlb", "🇹🇼 中華職棒 CPBL": "custom_cpbl"},
    "🏒 冰球": {"NHL": "icehockey_nhl"},
    "🏈 美式足球": {"NFL": "americanfootball_nfl"},
}
MARKETS = ["不讓分", "讓分盤", "大小分"]

MODES = [
    "🎟️ 純 N 串 1",
    "🛡️ 2 串 1 容錯",
    "🎯 單場獨立",
    "🗻 富士組合 (3場7注 Patent)",
    "🗽 洋基組合 (4場11注 Yankee)",
    "⚡ 4 串 6 (4場6組2串1)"
]

CURRENCIES = {
    "新台幣 (TWD)": "NT$",
    "澳門幣 (MOP)": "MOP$",
    "港幣 (HKD)": "HK$",
    "美金 (USD)": "US$"
}
TZ = dt.timezone(dt.timedelta(hours=8))


def cn(n):
    return f"{TEAMS.get(n, '')} {n}".strip()


def sn(n):
    return TEAMS.get(n, n)


def fair(prices):
    inv = [1 / p for p in prices]
    s = sum(inv)
    return [x / s for x in inv]


def load_cpbl_mock():
    rows = [
        ("cpbl1|不讓分|中信兄弟 勝 (主)", "cpbl1", "中信兄弟 (主) vs 統一7-ELEVEn獅 (客)", "18:35", "不讓分", "中信兄弟 勝 (主)", 1.75, 0.54, 0.05, "中信兄弟", "統一7-ELEVEn獅", "中信兄弟 獨贏", "中信兄弟", "統一7-ELEVEn獅"),
        ("cpbl1|不讓分|統一7-ELEVEn獅 勝 (客)", "cpbl1", "中信兄弟 (主) vs 統一7-ELEVEn獅 (客)", "18:35", "不讓分", "統一7-ELEVEn獅 勝 (客)", 1.95, 0.46, -0.10, "中信兄弟", "統一7-ELEVEn獅", "統一獅 獨贏", "中信兄弟", "統一7-ELEVEn獅"),
        ("cpbl1|讓分盤|中信兄弟 讓分 (-1.5)", "cpbl1", "中信兄弟 (主) vs 統一7-ELEVEn獅 (客)", "18:35", "讓分盤", "中信兄弟 讓分 (-1.5)", 2.15, 0.43, -0.07, "中信兄弟", "統一7-ELEVEn獅", "中信兄弟 讓 -1.5", "中信兄弟", "統一7-ELEVEn獅"),
        ("cpbl1|讓分盤|統一7-ELEVEn獅 受讓 (+1.5)", "cpbl1", "中信兄弟 (主) vs 統一7-ELEVEn獅 (客)", "18:35", "讓分盤", "統一7-ELEVEn獅 受讓 (+1.5)", 1.65, 0.57, 0.04, "中信兄弟", "統一7-ELEVEn獅", "統一獅 受讓 +1.5", "中信兄弟", "統一7-ELEVEn獅"),
        
        ("cpbl2|不讓分|樂天桃猿 勝 (主)", "cpbl2", "樂天桃猿 (主) vs 味全龍 (客)", "18:35", "不讓分", "樂天桃猿 勝 (主)", 1.80, 0.52, 0.04, "樂天桃猿", "味全龍", "樂天桃猿 獨贏", "樂天桃猿", "味全龍"),
        ("cpbl2|不讓分|味全龍 勝 (客)", "cpbl2", "樂天桃猿 (主) vs 味全龍 (客)", "18:35", "不讓分", "味全龍 勝 (客)", 1.90, 0.48, -0.08, "樂天桃猿", "味全龍", "味全龍 獨贏", "樂天桃猿", "味全龍"),
        ("cpbl2|大小分|大分 8.5", "cpbl2", "樂天桃猿 (主) vs 味全龍 (客)", "18:35", "大小分", "大分 8.5", 1.75, 0.54, 0.05, "樂天桃猿", "味全龍", "大分 8.5", "樂天桃猿", "味全龍"),
        ("cpbl2|大小分|小分 8.5", "cpbl2", "樂天桃猿 (主) vs 味全龍 (客)", "18:35", "大小分", "小分 8.5", 1.95, 0.46, -0.10, "樂天桃猿", "味全龍", "小分 8.5", "樂天桃猿", "味全龍"),
    ]
    cols = "id match_id match time type pick odds prob ev home away label hs aws".split()
    return pd.DataFrame(rows, columns=cols), None


@st.cache_data(ttl=600, show_spinner=False)
def load(key, sport):
    if sport == "custom_cpbl":
        return load_cpbl_mock()

    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
            params=dict(apiKey=key, regions="eu", markets="h2h,spreads,totals",
                        oddsFormat="decimal"), timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        if getattr(e.response, "status_code", None) in (404, 422):
            return None, "此聯賽目前不在 API 提供範圍，或尚未開季。"
        return None, f"連線失敗：{type(e).__name__}"
    if not data:
        return None, "目前暫無開盤數據"

    rows = []
    for m in data:
        home, mid = m["home_team"], m["id"]
        title = f"{cn(home)} (主) vs {cn(m['away_team'])} (客)"
        t = dt.datetime.fromisoformat(m["commence_time"].replace("Z", "+00:00"))
        t = t.astimezone(TZ).strftime("%m-%d %H:%M")

        agg = defaultdict(lambda: [[], 0.0])
        for bk in m["bookmakers"]:
            for mk in bk["markets"]:
                outs = mk["outcomes"]
                if any(o["price"] <= 1 for o in outs):
                    continue
                for o, p in zip(outs, fair([o["price"] for o in outs])):
                    a = agg[(mk["key"], o["name"], o.get("point"))]
                    a[0].append(p)
                    a[1] = max(a[1], o["price"])
        res = {k: (sum(v[0]) / len(v[0]), v[1]) for k, v in agg.items()}
        draw = res.get(("h2h", "Draw", None), (0, 0))[0]

        def add(typ, pick, odds, p, label):
            rows.append((f"{mid}|{typ}|{pick}", mid, title, t, typ, pick,
                         round(odds, 2), round(p, 4), round(p * odds - 1, 3),
                         cn(home), cn(m["away_team"]), label,
                         sn(home), sn(m["away_team"])))

        for (mk, name, pt), (p, o) in res.items():
            if mk == "h2h":
                if name == "Draw":
                    add("不讓分", "全場和局", o, p, "和局")
                else:
                    add("不讓分", f"{cn(name)} 勝 ({'主' if name == home else '客'})",
                        o, p, f"{sn(name)} 獨贏")
                    if draw:
                        add("雙重機會", f"🛡️ {cn(name)} 勝或和", 0.95 / (p + draw),
                            p + draw, f"{sn(name)} 不敗")
            elif mk == "spreads":
                if pt is not None:
                    pt = pt or 0
                    add("讓分盤", f"{cn(name)} 讓分 ({pt:+g})", o, p,
                        f"{sn(name)} {'受讓' if pt > 0 else '讓'} {pt:+g}")
            else:
                if pt is not None:
                    add("大小分", f"{'大' if name == 'Over' else '小'}分 {pt}", o, p,
                        f"{'大' if name == 'Over' else '小'}分 {pt}")

    cols = "id match_id match time type pick odds prob ev home away label hs aws".split()
    return pd.DataFrame(rows, columns=cols), None


LOG = "data/picks.csv"
SNAPS = "data/snapshots.csv"
LEAGUE_BY_SPORT = {v: k for cat in LEAGUES.values() for k, v in cat.items()}


def load_log():
    cols = "match_id sport commence first_seen home away market team point odds prob ev result"
    if not os.path.exists(LOG):
        return pd.DataFrame(columns=cols.split())
    return pd.read_csv(LOG, dtype={"result": str}).fillna({"result": ""})


@st.cache_data(ttl=600)
def load_snaps():
    return pd.read_csv(SNAPS) if os.path.exists(SNAPS) else pd.DataFrame()


def track_panel():
    log = load_log()
    done = log[log.result.isin(["贏", "輸"])]
    n = len(done)
    wins = (done.result == "贏").sum()
    roi = ((done.odds - 1).where(done.result == "贏", -1)).mean() if n else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("已記錄推薦", len(log))
    c2.metric("已結算", n)
    c3.metric("命中率", f"{wins / n:.0%}" if n else "—")
    c4.metric("平注報酬率", f"{roi:+.1%}" if n else "—")
    st.caption("資料由 GitHub Actions 每日自動收集與結算，推薦於開賽前記錄、不事後修改。"
               + (" ⚠️ 樣本數低於 30，數字參考價值有限。" if n < 30 else ""))
    st.download_button("⬇️ 下載完整紀錄 (CSV)", log.to_csv(index=False).encode("utf-8-sig"),
                       "picks.csv", use_container_width=True)
    if not log.empty:
        st.dataframe(log.iloc[::-1].head(30), use_container_width=True, hide_index=True)


def pick_card(df, league):
    c = df[(df.type == "不讓分") & (df.odds >= 1.3) & ~df.pick.str.contains("和局")]
    if c.empty:
        return
    r = c.loc[c.prob.idxmax()]
    st.markdown(f"""
<div style="background:#0f172a;border:1px solid #1e3a34;border-radius:18px;padding:18px;margin-bottom:12px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <b style="color:#fbbf24;font-size:18px">👑 今日 AI 首選 (澳門彩票 & 台灣運彩即時參考)</b>
    <span style="background:#064e3b;color:#34d399;padding:4px 10px;border-radius:99px;font-size:12px">● 即時開盤</span>
  </div>
  <div style="margin:12px 0 8px">
    <span style="background:#422006;color:#fbbf24;padding:3px 10px;border-radius:99px;font-size:12px">⭐ 每日一推</span>
    <span style="background:#052e2b;color:#34d399;padding:3px 10px;border-radius:99px;font-size:12px">{r.type}</span>
  </div>
  <div style="color:#94a3b8;font-size:13px">{league} · {r.time}</div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0;color:#f1f5f9;font-size:17px;font-weight:700">
    <div style="flex:1"><small style="color:#94a3b8;font-weight:400">客場</small><br>{r.away}</div>
    <div style="color:#64748b;padding:0 8px">VS</div>
    <div style="flex:1;text-align:right"><small style="color:#94a3b8;font-weight:400">主場</small><br>{r.home}</div>
  </div>
  <hr style="border-color:#1e293b">
  <div style="color:#94a3b8;font-size:13px">AI 推薦(獨贏)</div>
  <div style="color:#34d399;font-size:18px;font-weight:700;margin:4px 0 12px">{r.pick}</div>
  <div style="display:flex;gap:24px">
    <div><small style="color:#94a3b8">賠率</small><br><b style="color:#f1f5f9;font-size:22px">{r.odds}</b></div>
    <div style="flex:1"><small style="color:#94a3b8">共識機率</small><br>
      <b style="color:#f1f5f9;font-size:22px">{r.prob:.0%}</b>
      <div style="background:#1e293b;border-radius:99px;height:6px;margin-top:6px">
        <div style="width:{r.prob * 100:.0f}%;height:6px;border-radius:99px;background:linear-gradient(90deg,#34d399,#38bdf8)"></div>
      </div></div>
  </div>
</div>""", unsafe_allow_html=True)


def betslip(items, mode, budget, curr_symbol):
    c1, c2 = st.columns([3, 1])
    with c1:
        st.write(f"已選擇 **{len(items)}** 項賽事")
    with c2:
        if st.button("🗑️ 清空注單", key="clear_cart_btn"):
            st.session_state.cart.clear()
            st.rerun()

    tickets = []

    # 1. 基礎模式拆單
    if mode == "🎟️ 純 N 串 1":
        tickets = [tuple(items)]
    elif mode == "🛡️ 2 串 1 容錯":
        tickets = list(itertools.combinations(items, 2))
    elif mode == "🎯 單場獨立":
        tickets = [(i,) for i in items]

    # 2. 🗻 富士組合 Patent (3場7注: 3個單場 + 3個2串1 + 1個3串1)
    elif mode == "🗻 富士組合 (3場7注 Patent)":
        if len(items) != 3:
            return st.warning("⚠️ 富士組合 (Patent) **專用 3 場賽事**！請調整勾選數量至 3 場。")
        combos_1 = [(i,) for i in items]
        combos_2 = list(itertools.combinations(items, 2))
        combos_3 = [tuple(items)]
        tickets = combos_1 + combos_2 + combos_3

    # 3. 🗽 洋基組合 Yankee (4場11注: 6個2串1 + 4個3串1 + 1個4串1)
    elif mode == "🗽 洋基組合 (4場11注 Yankee)":
        if len(items) != 4:
            return st.warning("⚠️ 洋基組合 (Yankee) **專用 4 場賽事**！請調整勾選數量至 4 場。")
        combos_2 = list(itertools.combinations(items, 2))
        combos_3 = list(itertools.combinations(items, 3))
        combos_4 = [tuple(items)]
        tickets = combos_2 + combos_3 + combos_4

    # 4. ⚡ 4 串 6 (4場6組2串1)
    elif mode == "⚡ 4 串 6 (4場6組2串1)":
        if len(items) != 4:
            return st.warning("⚠️ 4 串 6 **專用 4 場賽事**！請調整勾選數量至 4 場。")
        tickets = list(itertools.combinations(items, 2))

    if not tickets:
        return st.warning("請在左側勾選適當場數！")

    unit = budget / len(tickets)
    st.markdown(f"**{mode}**：共 **{len(tickets)} 注** ｜ 每注 {curr_symbol} {unit:.2f} (總預算 {curr_symbol} {budget:,.2f})")

    total_payout = 0
    all_win_prob = prod(i["prob"] for i in items)

    for n, tk in enumerate(tickets, 1):
        o = prod(i["odds"] for i in tk)
        p = prod(i["prob"] for i in tk)
        payout = unit * o
        total_payout += payout
        st.info(f"**#{n}** " + " + ".join(f"`{i['pick']}`" for i in tk) +
                f"\n\n賠率 **{o:.2f}** ｜ 過關率 **{p:.1%}** ｜ 命中派彩 **{curr_symbol} {payout:,.2f}**")

    # 4串6 vs Yankee 對比展示
    if len(items) == 4 and ("Yankee" in mode or "4 串 6" in mode):
        st.markdown("---")
        st.subheader("📊 4串6 vs Yankee（洋基組合）對比分析")
        
        y_tickets = list(itertools.combinations(items, 2)) + list(itertools.combinations(items, 3)) + [tuple(items)]
        c6_tickets = list(itertools.combinations(items, 2))
        
        y_unit = budget / 11
        c6_unit = budget / 6
        
        y_max_payout = sum(y_unit * prod(i["odds"] for i in tk) for tk in y_tickets)
        c6_max_payout = sum(c6_unit * prod(i["odds"] for i in tk) for tk in c6_tickets)
        
        st.markdown(f"""
        * **中 2 場情況**：4串6 與 Yankee 都**至少命中 1 注 2串1**，皆能開始獲得派彩（最低過關門檻一致）。
        * **中 3 場情況**：4串6 獲得 **3 注 2串1**；Yankee 則可獲得 **3 注 2串1 + 1 注 3串1**，Yankee 派彩開始超越 4串6。
        * **全中 4 場極致爆發力**：
          * **4 串 6 (6注)**：最高派彩 **{curr_symbol} {c6_max_payout:,.2f}**
          * **Yankee (11注)**：最高派彩 **{curr_symbol} {y_max_payout:,.2f}** (包含 4串1 高倍率疊加)
        """)


@st.fragment
def board(df, mode, budget, curr_symbol):
    left, right = st.columns([7, 5])
    
    with left:
        if df.empty:
            st.warning("無符合條件的選項")
        for _, g in df.groupby("match_id", sort=False):
            f = g.iloc[0]
            with st.expander(f"🏆 {f.match}  ⏰ {f.time}", expanded=True):
                for typ, tg in g.groupby("type", sort=False):
                    st.markdown(f"**【{typ}】**")
                    for idx, r in enumerate(tg.to_dict("records")):
                        unique_key = f"{r['id']}_{idx}"
                        is_checked = unique_key in st.session_state.cart
                        
                        checked = st.checkbox(
                            f"{r['pick']} | 賠率 {r['odds']} (機率 {r['prob']:.0%})",
                            value=is_checked,
                            key=unique_key
                        )
                        
                        if checked and not is_checked:
                            st.session_state.cart[unique_key] = r
                        elif not checked and is_checked:
                            st.session_state.cart.pop(unique_key, None)

    with right:
        st.subheader("🧾 複式組合自選投注單")
        
        cart_items = list(st.session_state.cart.values())
        if cart_items:
            betslip(cart_items, mode, budget, curr_symbol)
        else:
            st.info("👈 請在左側勾選賽事，即可進行富士組合、Yankee 洋基組合與 4 串 6 的試算！")


def custom_odds_input_panel(curr_symbol):
    st.subheader("✍️ 台灣運彩 / 澳門彩票 實體賠率手動輸入與試算")
    st.caption("輸入實體彩券行的開盤賠率，快速進行過關率與預期收益試算：")

    col1, col2 = st.columns(2)
    with col1:
        match_name = st.text_input("賽事名稱", "中信兄弟 vs 統一獅")
        pick_name = st.text_input("選擇項目", "中信兄弟 獨贏")
    with col2:
        tslc_odds = st.number_input("實體賠率", min_value=1.01, value=1.75, step=0.05)
        custom_budget = st.number_input("投注金額", min_value=10, value=1000, step=100)

    est_prob = round(1 / tslc_odds, 4) if tslc_odds > 0 else 0.5
    est_payout = round(custom_budget * tslc_odds, 2)

    st.success(f"""
    📌 **【{match_name}】 ➔ {pick_name}**
    * **實體賠率**：`{tslc_odds}` ｜ **估計隱含勝率**：`{est_prob:.1%}`
    * **投注金額**：`{curr_symbol} {custom_budget:,.2f}`
    * 💰 **命中預計派彩**：`{curr_symbol} {est_payout:,.2f}`
    """)


# ---------------------------- 主程式 ----------------------------
if not st.session_state.get("ok"):
    _, c, _ = st.columns([1, 2, 1])
    with c:
        st.title("🔒 登入")
        pwd = st.text_input("密碼", type="password")
        if st.button("登入", use_container_width=True):
            if pwd == st.secrets["APP_PASSWORD"]:
                st.session_state.ok = True
                st.rerun()
            st.error("密碼錯誤")
    st.stop()

sb = st.sidebar
if sb.button("🔒 登出", use_container_width=True):
    st.session_state.ok = False
    st.rerun()

curr_name = sb.selectbox("💱 選擇顯示幣值", list(CURRENCIES.keys()), index=0)
curr_symbol = CURRENCIES[curr_name]

cat = sb.selectbox("體育項目", LEAGUES)
league = sb.selectbox("聯賽", LEAGUES[cat])
mode = sb.radio("下注模式", MODES)
min_p = sb.slider("機率門檻 (%)", 40, 90, 50, 5) / 100
opts = MARKETS + (["雙重機會"] if "足球" in cat else [])
shown = sb.multiselect("顯示玩法(空=全部)", opts) or opts
budget = sb.number_input(f"總資金 ({curr_symbol})", 10, value=1000, step=100)

if sb.button("🔄 刷新數據", use_container_width=True):
    load.clear()
    st.rerun()

st.title("⚡ ODD-HUNTER ｜ 澳門彩票 & 台灣運彩 AI 決策中心")
st.caption(f"📡 整合 Macauslot / TSLC 即時參考盤口 ｜ 當前貨幣單位：**{curr_name} ({curr_symbol})**")

with st.spinner("抓取數據中..."):
    df_all, err = load(st.secrets["ODDS_API_KEY"], LEAGUES[cat][league])
if err:
    st.error(err)
    st.stop()

pick_card(df_all, league)
t1, t3, t2, t4, t5 = st.tabs(
    ["📋 盤口與注單", "🤖 AI 推薦", "✍️ 實體運彩輸入", "📊 公開戰績", "🧮 統計分析"])

with t3:
    st.caption("AI 推薦：每場取共識機率最高的獨贏或讓分選項")
    for _, g in df_all[df_all.prob >= 0.7].groupby("match_id", sort=False):
        st.markdown(f"#### 🏆 {g.iloc[0].match} ⏰ {g.iloc[0].time}")
        for r in g.itertuples():
            st.success(f"**{r.pick}** ｜ 賠率 `{r.odds}` ｜ 機率 `{r.prob:.1%}` ｜ EV `{r.ev:+.3f}`")

with t2:
    custom_odds_input_panel(curr_symbol)

with t4:
    track_panel()

with t5:
    pass

with t1:
    board(df_all[(df_all.prob >= min_p) & df_all.type.isin(shown)], mode, budget, curr_symbol)
