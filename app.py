import datetime as dt
import itertools
import math
import os
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


def sn(n):
    return TEAMS.get(n, n)


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
                    if draw:  # 雙重機會(估算賠率,以莊家實際為準)
                        add("雙重機會", f"🛡️ {cn(name)} 勝或和", 0.95 / (p + draw),
                            p + draw, f"{sn(name)} 不敗")
            elif mk == "spreads":
                pt = pt or 0
                add("讓分盤", f"{cn(name)} 讓分 ({pt:+g})", o, p,
                    f"{sn(name)} {'受讓' if pt > 0 else '讓'} {pt:+g}")
            else:
                add("大小分", f"{'大' if name == 'Over' else '小'}分 {pt}", o, p,
                    f"{'大' if name == 'Over' else '小'}分 {pt}")

    cols = "id match_id match time type pick odds prob ev home away label hs aws".split()
    return pd.DataFrame(rows, columns=cols), None


LOG = "pick_log.csv"  # 注意:Streamlit Cloud 重啟後會重置,長期保存請改用外部資料庫
LOG_COLS = "match_id time league pick side odds prob sport result".split()


def load_log():
    if os.path.exists(LOG):
        return pd.read_csv(LOG, dtype={"result": str}).fillna({"result": ""})
    return pd.DataFrame(columns=LOG_COLS)


def log_pick(r, league, sport):
    """每場比賽只記錄一次首選(開賽前記錄,不事後修改)"""
    log = load_log()
    if r.match_id in set(log.match_id):
        return
    row = dict(match_id=r.match_id, time=r.time, league=league, pick=r.pick,
               side="主" if r.pick.endswith("(主)") else "客",
               odds=r.odds, prob=r.prob, sport=sport, result="")
    pd.concat([log, pd.DataFrame([row])]).to_csv(LOG, index=False)


def settle(key):
    """用 API 比分結算(僅限近 3 天完賽;平手視為獨贏輸)。按鈕觸發以節省額度"""
    log = load_log()
    for sport in log[log.result == ""].sport.unique():
        try:
            r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/scores/",
                             params=dict(apiKey=key, daysFrom=3), timeout=10)
            r.raise_for_status()
        except requests.RequestException:
            continue
        done = {e["id"]: e for e in r.json() if e.get("completed") and e.get("scores")}
        for i, p in log[(log.result == "") & (log.sport == sport)].iterrows():
            e = done.get(p.match_id)
            if not e:
                continue
            sc = {s["name"]: float(s["score"]) for s in e["scores"]}
            h, a = sc.get(e["home_team"]), sc.get(e["away_team"])
            if h is None or a is None:
                continue
            win = h > a if p.side == "主" else a > h
            log.loc[i, "result"] = "贏" if win else "輸"
    log.to_csv(LOG, index=False)


def track_panel(key):
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
    st.caption("所有數字均由本站實際記錄與賽果計算,非預測保證。"
               + (" ⚠️ 樣本數低於 30,數字參考價值有限。" if n < 30 else ""))
    b1, b2 = st.columns(2)
    if b1.button("🔄 更新賽果", use_container_width=True):
        settle(key)
        st.rerun()
    b2.download_button("⬇️ 下載完整紀錄 (CSV)", log.to_csv(index=False).encode("utf-8-sig"),
                       "pick_log.csv", use_container_width=True)
    if not log.empty:
        st.dataframe(log.iloc[::-1].head(30), use_container_width=True, hide_index=True)


def pick_card(df, league, sport=None):
    """今日首選卡片:不讓分中、共識機率最高(賠率 ≥ 1.3)的選項"""
    c = df[(df.type == "不讓分") & (df.odds >= 1.3) & ~df.pick.str.contains("和局")]
    if c.empty:
        return
    r = c.loc[c.prob.idxmax()]
    if sport:
        log_pick(r, league, sport)
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


def ai_list(df):
    """每場挑一個共識機率最高的獨贏/讓分選項,以金色標籤列出"""
    c = df[df.type.isin(["不讓分", "讓分盤"]) & (df.label != "和局")]
    if c.empty:
        return st.info("暫無資料")
    top = c.loc[c.groupby("match_id").prob.idxmax()].sort_values("time")
    html = "".join(
        '<div style="display:flex;align-items:center;gap:10px;padding:14px 10px;'
        'border-bottom:1px solid #1e293b">'
        f'<div style="flex:1;color:#94a3b8;font-size:12px">{r.time}<br>'
        f'<span style="color:#f1f5f9;font-size:15px">{r.aws} vs {r.hs}</span></div>'
        '<span style="background:linear-gradient(#fcd34d,#f59e0b);color:#451a03;'
        f'font-weight:800;padding:8px 14px;border-radius:12px;white-space:nowrap">{r.label}</span>'
        f'<small style="color:#94a3b8;min-width:32px">{r.prob:.0%}</small></div>'
        for r in top.itertuples()
    )
    st.caption("AI 推薦:每場取共識機率最高的獨贏或讓分選項(客 vs 主)")
    st.markdown(f'<div style="background:#0b0f19;border-radius:14px">{html}</div>',
                unsafe_allow_html=True)


def wilson(w, n, z=1.96):
    """命中率的 95% Wilson 信賴區間"""
    if n == 0:
        return 0.0, 0.0
    p, d = w / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def stats_tab(df):
    # ---------- 1. 定義問題 ----------
    st.header("1️⃣ 定義問題")
    st.markdown("""
**研究目的**:檢驗本站「機率與推薦」的資料品質與實際表現。

- **Q1** 各玩法的機率、賠率、EV 分布為何?(描述統計)
- **Q2** 莊家抽水(總隱含機率超出 100% 的部分)有多大?
- **Q3** 首選推薦的實際命中率,是否與預測機率一致?(校準度)
- **Q4** 照首選平注下注,長期報酬率為何?

**變數**:預測機率 `prob`(多家莊家去水後平均)、賠率 `odds`、期望值 `EV = prob × odds − 1`、賽果(贏/輸)。
""")

    # ---------- 2. 收集資料 ----------
    st.header("2️⃣ 收集資料")
    log = load_log()
    done = log[log.result.isin(["贏", "輸"])].copy()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("盤口選項數", len(df))
    c2.metric("比賽場次", df.match_id.nunique())
    c3.metric("推薦紀錄", len(log))
    c4.metric("已結算", len(done))
    st.caption("資料來源:The Odds API(目前所選聯賽的即時盤口)與本站 `pick_log.csv` 推薦紀錄。")

    # ---------- 3. 整理與計算 ----------
    st.header("3️⃣ 整理與計算")
    st.subheader("Q1 各玩法描述統計")
    desc = df.groupby("type").agg(
        筆數=("prob", "size"), 平均機率=("prob", "mean"), 機率標準差=("prob", "std"),
        平均賠率=("odds", "mean"), 平均EV=("ev", "mean"),
        正EV比例=("ev", lambda s: (s > 0).mean()),
    ).round(3)
    st.dataframe(desc, use_container_width=True)
    st.download_button("⬇️ 下載描述統計 (CSV)", desc.to_csv().encode("utf-8-sig"),
                       "descriptive_stats.csv")

    st.subheader("Q2 莊家抽水")
    ml = df[df.type == "不讓分"].groupby("match_id").odds.agg(lambda s: (1 / s).sum())
    ml = ml[ml > 0]
    if len(ml):
        st.metric("獨贏盤平均總隱含機率", f"{ml.mean():.1%}",
                  f"抽水約 {ml.mean() - 1:+.1%}", delta_color="off")
        st.caption("以各選項最佳賠率計算;超過 100% 的部分即莊家優勢,低於 100% 代表跨莊有套利空間。")

    st.subheader("Q3、Q4 首選推薦實際表現")
    n = len(done)
    if n == 0:
        st.info("尚無已結算資料。請先累積推薦紀錄,並在「公開戰績」分頁按「更新賽果」。")
    else:
        done["win"] = (done.result == "贏").astype(int)
        w = int(done.win.sum())
        lo, hi = wilson(w, n)
        exp = done.prob.sum()
        var = (done.prob * (1 - done.prob)).sum()
        z = (w - exp) / math.sqrt(var) if var else 0.0
        pval = math.erfc(abs(z) / math.sqrt(2))
        brier = ((done.prob - done.win) ** 2).mean()
        roi = (done.odds - 1).where(done.win == 1, -1).mean()
        m = st.columns(4)
        m[0].metric("命中率", f"{w / n:.1%}", f"95% CI {lo:.0%}–{hi:.0%}", delta_color="off")
        m[1].metric("預期命中率", f"{exp / n:.1%}")
        m[2].metric("Brier 分數", f"{brier:.3f}", help="越低越準;永遠猜 50% 為 0.25")
        m[3].metric("平注報酬率", f"{roi:+.1%}")

        done["區間"] = pd.cut(done.prob, [0, .5, .6, .7, .8, 1.0])
        cal = done.groupby("區間", observed=True).agg(
            場次=("win", "size"), 預測機率=("prob", "mean"), 實際命中率=("win", "mean")).round(3)
        cal.index = cal.index.astype(str)

    # ---------- 4. 分析與呈現 ----------
    st.header("4️⃣ 分析與呈現")
    st.subheader("EV 分布")
    h = pd.cut(df.ev, 10).value_counts().sort_index()
    h.index = h.index.astype(str)
    st.bar_chart(h)

    if n:
        st.subheader("校準圖:預測機率 vs 實際命中率")
        st.bar_chart(cal[["預測機率", "實際命中率"]])
        st.dataframe(cal, use_container_width=True)

    st.subheader("結論")
    pos = (df.ev > 0).mean()
    st.markdown(f"- **Q1**:{pos:.0%} 的選項 EV > 0;共識機率與最佳賠率的差距造成少數正 EV。")
    if len(ml):
        st.markdown(f"- **Q2**:獨贏盤平均抽水約 {ml.mean() - 1:+.1%},長期下注需先克服這個成本。")
    if n < 30:
        st.markdown(f"- **Q3、Q4**:目前僅 {n} 場已結算,**樣本不足(建議 ≥ 30,最好 ≥ 100)**,不下結論。")
    else:
        verdict = ("與預期**有顯著差異**" if pval < 0.05 else "與預期**無顯著差異**")
        st.markdown(f"- **Q3**:實際命中 {w / n:.1%} vs 預期 {exp / n:.1%},z = {z:.2f},"
                    f"p = {pval:.3f},{verdict}(α = 0.05)。")
        st.markdown(f"- **Q4**:平注報酬率 {roi:+.1%};請對照信賴區間,短期結果變動很大。")
    st.caption("限制:機率來自市場共識而非獨立模型;首選為規則挑選,有選擇偏誤;"
               "常態近似與 Wilson 區間在小樣本下較不準;過去表現不代表未來。")


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

pick_card(df_all, league, LEAGUES[cat][league])
t1, t3, t2, t4, t5 = st.tabs(
    ["📋 盤口與注單", "🤖 AI 推薦", "🔥 高機率選項", "📊 公開戰績", "🧮 統計分析"])
with t3:
    ai_list(df_all)
with t4:
    track_panel(st.secrets["ODDS_API_KEY"])
with t5:
    stats_tab(df_all)
with t1:
    board(df_all[(df_all.prob >= min_p) & df_all.type.isin(shown)], mode, budget)
with t2:
    st.caption("機率為多家莊家去水後共識;高機率通常賠率很低,不等於高價值。")
    for _, g in df_all[df_all.prob >= 0.7].groupby("match_id", sort=False):
        st.markdown(f"#### 🏆 {g.iloc[0].match} ⏰ {g.iloc[0].time}")
        for r in g.itertuples():
            st.success(f"**{r.pick}** ｜ 賠率 `{r.odds}` ｜ 機率 `{r.prob:.1%}` ｜ EV `{r.ev:+.3f}`")
