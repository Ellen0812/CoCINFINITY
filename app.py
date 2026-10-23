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


# -------------------------------------------------------------------
# 中華職棒 (CPBL) 本地預設開盤資料庫
# -------------------------------------------------------------------
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
            return None, "此聯賽目前不在 The Odds API 提供範圍,或尚未開季。"
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
    st.caption("資料由 GitHub Actions 每日自動收集與結算,推薦於開賽前記錄、不事後修改。"
               + (" ⚠️ 樣本數低於 30,數字參考價值有限。" if n < 30 else ""))
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


@st.fragment
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
                    for idx, r in enumerate(tg.to_dict("records")):
                        unique_key = f"{r['id']}_{idx}"
                        if st.checkbox(f"{r['pick']} | {r['odds']} ({r['prob']:.0%})",
                                       key=unique_key):
                            sel.append(r)
    with right:
        st.subheader("🧾 投注單試算")
        if sel:
            betslip(sel, mode, budget)
        else:
            st.info("👈 勾選選項開始試算")


def ai_list(df):
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
    if n == 0:
        return 0.0, 0.0
    p, d = w / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def stats_tab(df):
    st.header("1️⃣ 定義問題")
    st.markdown("""
**研究目的**:長期追蹤並檢驗「機率與推薦」的資料品質與實際表現。

- **Q1** 各玩法的機率、賠率、EV 分布為何?
- **Q2** 莊家抽水(總隱含機率超出 100% 的部分)多大?隨時間是否變化?
- **Q3** 推薦的實際命中率是否與預測機率一致?(校準度)
- **Q4** 照推薦平注下注,報酬率為何?
- **Q5** 表現是否因聯賽、玩法、時間(週)而不同?

**變數**:預測機率 `prob`(多家莊家去水後平均)、賠率 `odds`、`EV = prob × odds − 1`、賽果(贏/輸/退)。
""")

    st.header("2️⃣ 收集資料")
    log, snaps = load_log(), load_snaps()
    done = log[log.result.isin(["贏", "輸"])].copy()
    c = st.columns(4)
    if len(log):
        t0, t1 = pd.to_datetime(log.first_seen, utc=True).agg(["min", "max"])
        c[0].metric("收集期間", f"{t0:%m/%d}–{t1:%m/%d}")
    else:
        c[0].metric("收集期間", "—")
    c[1].metric("推薦紀錄", len(log))
    c[2].metric("已結算", len(done))
    c[3].metric("盤口快照", f"{len(snaps):,}")
    st.caption("每日自動收集(排程至 2027-01-14),來源 The Odds API。"
               "目前所選聯賽的即時盤口用於 Q1。")

    st.header("3️⃣ 整理與計算")
    st.subheader("Q1 各玩法描述統計(即時盤口)")
    desc = df.groupby("type").agg(
        筆數=("prob", "size"), 平均機率=("prob", "mean"), 機率標準差=("prob", "std"),
        平均賠率=("odds", "mean"), 平均EV=("ev", "mean"),
        正EV比例=("ev", lambda s: (s > 0).mean()),
    ).round(3)
    st.dataframe(desc, use_container_width=True)
    st.download_button("⬇️ 下載描述統計 (CSV)", desc.to_csv().encode("utf-8-sig"),
                       "descriptive_stats.csv")

    st.subheader("Q2 莊家抽水")
    ov = None
    h2h = snaps[snaps.market == "h2h"] if len(snaps) else snaps
    if len(h2h):
        per = (h2h.assign(day=h2h.snapshot_at.str[:10])
               .groupby(["day", "match_id"]).odds.agg(lambda s: (1 / s).sum()))
        ov = per.groupby("day").mean()
        st.line_chart(ov.rename("獨贏盤總隱含機率"))
    else:
        live = df[df.type == "不讓分"].groupby("match_id").odds.agg(lambda s: (1 / s).sum())
        ov = live[live > 0]
    if len(ov):
        st.metric("獨贏盤平均總隱含機率", f"{ov.mean():.1%}",
                  f"抽水約 {ov.mean() - 1:+.1%}", delta_color="off")
    st.caption("以各選項最佳賠率計算;超過 100% 為莊家優勢,低於 100% 代表跨莊有套利空間。")

    st.subheader("Q3–Q5 推薦實際表現")
    n = len(done)
    if n == 0:
        st.info("尚無已結算資料,等 collector 累積賽果後這裡會自動出現。")
    else:
        done["win"] = (done.result == "贏").astype(int)
        done["roi"] = (done.odds - 1).where(done.win == 1, -1)
        done["date"] = pd.to_datetime(done.commence, utc=True).dt.tz_convert("Asia/Taipei")
        done = done.sort_values("date")
        done["聯賽"] = done.sport.map(LEAGUE_BY_SPORT).fillna(done.sport)
        done["玩法"] = done.market.map({"h2h": "獨贏", "spreads": "讓分"})
        done["週"] = done.date.dt.strftime("%G-W%V")

        w = int(done.win.sum())
        lo, hi = wilson(w, n)
        exp = done.prob.sum()
        var = (done.prob * (1 - done.prob)).sum()
        z = (w - exp) / math.sqrt(var) if var else 0.0
        pval = math.erfc(abs(z) / math.sqrt(2))
        brier = ((done.prob - done.win) ** 2).mean()
        roi = done.roi.mean()
        m = st.columns(4)
        m[0].metric("命中率", f"{w / n:.1%}", f"95% CI {lo:.0%}–{hi:.0%}", delta_color="off")
        m[1].metric("預期命中率", f"{exp / n:.1%}")
        m[2].metric("Brier 分數", f"{brier:.3f}", help="越低越準;永遠猜 50% 為 0.25")
        m[3].metric("平注報酬率", f"{roi:+.1%}")

        agg = dict(場次=("win", "size"), 命中率=("win", "mean"),
                   預期機率=("prob", "mean"), 報酬率=("roi", "mean"))
        done["區間"] = pd.cut(done.prob, [0, .5, .6, .7, .8, 1.0])
        cal = done.groupby("區間", observed=True).agg(**agg).round(3)
        cal.index = cal.index.astype(str)
        weekly = done.groupby("週").agg(**agg).round(3)

    st.header("4️⃣ 分析與呈現")
    st.subheader("EV 分布(即時盤口)")
    hist = pd.cut(df.ev, 10).value_counts().sort_index()
    hist.index = hist.index.astype(str)
    st.bar_chart(hist)

    if n:
        st.subheader("累積命中率走勢")
        st.line_chart(done.set_index("date").win.expanding().mean().rename("累積命中率"))
        st.subheader("校準圖:預測機率 vs 實際命中率")
        st.bar_chart(cal[["預期機率", "命中率"]])
        st.dataframe(cal, use_container_width=True)
        st.subheader("每週表現")
        st.bar_chart(weekly[["預期機率", "命中率"]])
        st.dataframe(weekly, use_container_width=True)
        for col in ("聯賽", "玩法"):
            st.subheader(f"依{col}")
            st.dataframe(done.groupby(col).agg(**agg).round(3), use_container_width=True)

    st.subheader("結論")
    st.markdown(f"- **Q1**:即時盤口中 {(df.ev > 0).mean():.0%} 的選項 EV > 0。")
    if len(ov):
        st.markdown(f"- **Q2**:獨贏盤平均抽水約 {ov.mean() - 1:+.1%},長期下注需先克服這個成本。")
    if n < 30:
        st.markdown(f"- **Q3–Q5**:目前僅 {n} 場已結算,**樣本不足(建議 ≥ 100)**,不下結論。")
    else:
        verdict = "與預期**有顯著差異**" if pval < 0.05 else "與預期**無顯著差異**"
        st.markdown(f"- **Q3**:實際命中 {w / n:.1%} vs 預期 {exp / n:.1%},z = {z:.2f},"
                    f"p = {pval:.3f},{verdict}(α = 0.05)。")
        st.markdown(f"- **Q4**:平注報酬率 {roi:+.1%};請對照信賴區間,短期變動很大。")
        st.markdown("- **Q5**:各分組樣本較少,差異請謹慎解讀(多重比較容易出現假象)。")
    st.caption("限制:機率來自市場共識而非獨立模型;推薦為規則挑選,有選擇偏誤;"
               "每日只抓一次盤口,非收盤賠率;過去表現不代表未來。")


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
t1, t3, t2, t4, t5 = st.tabs(
    ["📋 盤口與注單", "🤖 AI 推薦", "🔥 高機率選項", "📊 公開戰績", "🧮 統計分析"])
with t3:
    ai_list(df_all)
with t4:
    track_panel()
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
