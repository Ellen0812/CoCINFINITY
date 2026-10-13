import datetime as dt
import itertools
from collections import defaultdict
from math import prod

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="⚡ ODD-HUNTER", layout="wide")

TEAMS = dict(p.split("=") for p in """Arsenal=阿仙奴;Leeds United=列斯聯;Chelsea=車路士;
Bournemouth=般尼茅夫;Manchester United=曼聯;Tottenham Hotspur=熱刺;Liverpool=利物浦;
Manchester City=曼城;Aston Villa=阿士東維拉;Newcastle United=紐卡素;West Ham United=韋斯咸;
Fulham=富咸;Hull City=侯城;Ipswich Town=葉士域治;Brighton=白禮頓;Crystal Palace=水晶宮;
Brentford=賓福特;Everton=愛華頓;Coventry City=高雲地利;Detroit Pistons=底特律活塞;
Boston Celtics=波士頓塞爾特人;Real Madrid=皇家馬德里;Barcelona=巴塞隆拿;
Atletico Madrid=馬德里體育會;Los Angeles Lakers=洛杉磯湖人;Golden State Warriors=金州勇士;
Miami Heat=邁阿密熱火;Brooklyn Nets=布魯克林網;Phoenix Suns=菲尼克斯太陽;
Los Angeles Dodgers=洛杉磯道奇;New York Yankees=紐約洋基;Atlanta Braves=亞特蘭大勇士;
Houston Astros=休士頓太空人""".replace("\n", "").split(";"))

LEAGUES = {
    "⚽ 足球": {"英超 EPL": "soccer_epl", "西甲": "soccer_spain_la_liga",
              "意甲": "soccer_italy_serie_a", "德甲": "soccer_germany_bundesliga",
              "歐冠": "soccer_uefa_champs_league"},
    "🏀 籃球": {"NBA": "basketball_nba", "歐洲聯賽": "basketball_euroleague"},
    "⚾ 棒球": {"MLB": "baseball_mlb"},
    "🏒 冰球": {"NHL": "icehockey_nhl"},
    "🏈 美式足球": {"NFL": "americanfootball_nfl"},
}
MARKETS = ["不讓分", "讓分盤", "大小分"]
MODES = ["🎟️ 純 N 串 1", "🛡️ 2 串 1 容錯", "🎯 單場獨立"]
TZ = dt.timezone(dt.timedelta(hours=8))


def cn(n):
    return f"{TEAMS.get(n, '')} {n}".strip()


def fair(prices):
    """去水:隱含機率正規化為總和 1"""
    inv = [1 / p for p in prices]
    s = sum(inv)
    return [x / s for x in inv]


@st.cache_data(ttl=600, show_spinner=False)
def load(key, sport):
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
            params=dict(apiKey=key, regions="eu", markets="h2h,spreads,totals",
                        oddsFormat="decimal"), timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        return None, f"連線失敗：{type(e).__name__}"
    if not data:
        return None, "目前暫無開盤數據"

    rows = []
    for m in data:
        home, mid = m["home_team"], m["id"]
        title = f"{cn(home)} (主) vs {cn(m['away_team'])} (客)"
        t = dt.datetime.fromisoformat(m["commence_time"].replace("Z", "+00:00"))
        t = t.astimezone(TZ).strftime("%m-%d %H:%M")

        # 多家莊家:平均去水機率 + 最佳賠率
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

        def add(typ, pick, odds, p):
            rows.append((f"{mid}|{typ}|{pick}", mid, title, t, typ, pick,
                         round(odds, 2), round(p, 4), round(p * odds - 1, 3),
                         cn(home), cn(m["away_team"])))

        for (mk, name, pt), (p, o) in res.items():
            if mk == "h2h":
                if name == "Draw":
                    add("不讓分", "全場和局", o, p)
                else:
                    add("不讓分", f"{cn(name)} 勝 ({'主' if name == home else '客'})", o, p)
                    if draw:  # 雙重機會(估算賠率,以莊家實際為準)
                        add("雙重機會", f"🛡️ {cn(name)} 勝或和", 0.95 / (p + draw), p + draw)
            elif mk == "spreads":
                add("讓分盤", f"{cn(name)} 讓分 ({(pt or 0):+g})", o, p)
            else:
                add("大小分", f"{'大' if name == 'Over' else '小'}分 {pt}", o, p)

    cols = "id match_id match time type pick odds prob ev home away".split()
    return pd.DataFrame(rows, columns=cols), None


def pick_card(df, league):
    """今日首選卡片:不讓分中、共識機率最高(賠率 ≥ 1.3)的選項"""
    c = df[(df.type == "不讓分") & (df.odds >= 1.3) & ~df.pick.str.contains("和局")]
    if c.empty:
        return
    r = c.loc[c.prob.idxmax()]
    st.markdown(f"""
<div style="background:#0f172a;border:1px solid #1e3a34;border-radius:18px;padding:18px;margin-bottom:12px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <b style="color:#fbbf24;font-size:18px">👑 今日 AI 首選</b>
    <span style="background:#064e3b;color:#34d399;padding:4px 10px;border-radius:99px;font-size:12px">● 即時盤口</span>
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


def betslip(items, mode, budget):
    st.write(f"已選 **{len(items)}** 項")
    tickets = [[tuple(items)], list(itertools.combinations(items, 2)),
               [(i,) for i in items]][MODES.index(mode)]
    if not tickets:
        return st.warning("容錯模式需至少勾選 2 項")
    if mode == MODES[0] and len({i["match_id"] for i in items}) < len(items):
        st.warning("⚠️ 同場選項相關,多數莊家不允許串關")
    unit = budget / len(tickets)
    st.markdown(f"**{mode}**:{len(tickets)} 張 × $ {unit:.2f}(總 $ {budget})")
    for n, tk in enumerate(tickets, 1):
        o, p = prod(i["odds"] for i in tk), prod(i["prob"] for i in tk)
        st.info(f"**#{n}** " + " + ".join(f"`{i['pick']}`" for i in tk) +
                f"\n\n賠率 **{o:.2f}** ｜ 過關率 **{p:.1%}** ｜ 派彩 **${unit * o:,.2f}**")


@st.fragment  # 勾選只重繪此區塊,不會重跑整頁
def board(df, mode, budget):
    left, right = st.columns([7, 5])
    sel = []
    with left:
        if df.empty:
            st.warning("無符合條件的選項")
        for _, g in df.groupby("match_id", sort=False):
            f = g.iloc[0]
            with st.expander(f"🏆 {f.match}  ⏰ {f.time}", expanded=True):
                for typ, tg in g.groupby("type", sort=False):
                    st.markdown(f"**【{typ}】**")
                    for r in tg.to_dict("records"):
                        if st.checkbox(f"{r['pick']} | {r['odds']} ({r['prob']:.0%})",
                                       key=r["id"]):
                            sel.append(r)
    with right:
        st.subheader("🧾 投注單試算")
        betslip(sel, mode, budget) if sel else st.info("👈 勾選選項開始試算")


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
cat = sb.selectbox("體育項目", LEAGUES)
league = sb.selectbox("聯賽", LEAGUES[cat])
mode = sb.radio("下注模式", MODES)
min_p = sb.slider("機率門檻 (%)", 40, 90, 50, 5) / 100
opts = MARKETS + (["雙重機會"] if "足球" in cat else [])
shown = sb.multiselect("顯示玩法(空=全部)", opts) or opts
budget = sb.number_input("總資金 ($)", 10, value=100, step=10)
if sb.button("🔄 刷新", use_container_width=True):
    load.clear()
    st.rerun()

st.title("⚡ ODD-HUNTER")
with st.spinner("抓取數據中..."):
    df_all, err = load(st.secrets["ODDS_API_KEY"], LEAGUES[cat][league])
if err:
    st.error(err)
    st.stop()

pick_card(df_all, league)
t1, t2 = st.tabs(["📋 盤口與注單", "🔥 高機率選項"])
with t1:
    board(df_all[(df_all.prob >= min_p) & df_all.type.isin(shown)], mode, budget)
with t2:
    st.caption("機率為多家莊家去水後共識;高機率通常賠率很低,不等於高價值。")
    for _, g in df_all[df_all.prob >= 0.7].groupby("match_id", sort=False):
        st.markdown(f"#### 🏆 {g.iloc[0].match} ⏰ {g.iloc[0].time}")
        for r in g.itertuples():
            st.success(f"**{r.pick}** ｜ 賠率 `{r.odds}` ｜ 機率 `{r.prob:.1%}` ｜ EV `{r.ev:+.3f}`")
