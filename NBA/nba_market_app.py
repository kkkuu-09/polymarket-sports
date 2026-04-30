import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import altair as alt

# ========== 强制清空缓存 ==========
st.cache_data.clear()
st.cache_resource.clear()

# ========== 数据库配置 ==========
DB_CONFIG = {
    "host": "125.227.80.149",  # 你的公网IP
    "user": "root",
    "password": "123456",
    "database": "nba",
    "port": 3306
}
engine = create_engine(f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
st.set_page_config(layout="wide")
st.title("🏀 NBA 赛事数据查询系统")

# ========== 初始化默认值 ==========
default_values = {
    "event_key": "",
    "t1_key": "",
    "t2_key": "",
    "price_choose": "不限制价格",
    "price_min": 0.0,
    "price_max": 1.0,
    "page": 1
}
for key, val in default_values.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ========== 时间筛选 ==========
c1, c2 = st.columns(2)
with c1:
    s_date = st.date_input("开始日期", value=datetime.now().date())
    s_time = st.time_input("开始时间")
with c2:
    e_date = st.date_input("结束日期", value=datetime.now().date())
    e_time = st.time_input("结束时间")
start_dt = datetime.combine(s_date, s_time)
end_dt = datetime.combine(e_date, e_time)

# ========== 模糊搜索 ==========
c3, c4, c5 = st.columns(3)
with c3:
    event_key = st.text_input("比赛名称（模糊）", key="event_key")
with c4:
    t1_key = st.text_input("主队（模糊）", key="t1_key")
with c5:
    t2_key = st.text_input("客队（模糊）", key="t2_key")

# ========== 价格筛选 ==========
st.markdown("#### 赔率筛选")
cp1, cp2, cp3 = st.columns([1.2,1,1])
with cp1:
    price_choose = st.selectbox(
        "筛选目标", ["不限制价格","主队(price1)","客队(price2)"], key="price_choose"
    )
with cp2:
    price_min = st.number_input("赔率最低", min_value=0.0, value=0.0, step=0.01, key="price_min")
with cp3:
    price_max = st.number_input("赔率最高", min_value=0.0, value=1.0, step=0.01, key="price_max")

# ========== 排序 & 分页 ==========
sort_col = st.selectbox(
    "排序字段",["time_utc","id","price1","price2"],
    format_func=lambda x:{"time_utc":"时间","id":"ID","price1":"主队赔率","price2":"客队赔率"}[x]
)
sort_way = st.radio("排序", ["升序","降序"], horizontal=True)
sort_sql = "ASC" if sort_way == "升序" else "DESC"
page_size = st.selectbox("每页条数", [20,50,100], index=1)

# ========== 按钮：重置回调 ==========
def reset_filters():
    for key, val in default_values.items():
        st.session_state[key] = val

bt1, bt2, bt3 = st.columns(3)
with bt1:
    search_btn = st.button("🔍 查询数据", type="primary", use_container_width=True)
with bt2:
    st.button("🔄 重置条件", use_container_width=True, on_click=reset_filters)
with bt3:
    download_placeholder = st.empty()

# ========== 查询函数（表名：nba_market_price，和你图里一致） ==========
@st.cache_data(ttl=30)
def get_total(sd, ed, ev, t1, t2, p_choose, pmi, pma):
    base = """
    SELECT COUNT(*) AS cnt FROM nba_market_price
    WHERE time_utc BETWEEN %s AND %s
    AND event_title LIKE %s
    AND team1 LIKE %s
    AND team2 LIKE %s
    """
    params = (sd, ed, f"%{ev}%", f"%{t1}%", f"%{t2}%")
    if p_choose == "主队(price1)":
        base += " AND price1 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    elif p_choose == "客队(price2)":
        base += " AND price2 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    return pd.read_sql(base, engine, params=params).iloc[0]["cnt"]

@st.cache_data(ttl=30)
def get_data(sd, ed, ev, t1, t2, p_choose, pmi, pma, page, ps, sc, sw):
    off = (page-1)*ps
    base = """
    SELECT * FROM nba_market_price
    WHERE time_utc BETWEEN %s AND %s
    AND event_title LIKE %s
    AND team1 LIKE %s
    AND team2 LIKE %s
    """
    params = (sd, ed, f"%{ev}%", f"%{t1}%", f"%{t2}%")
    if p_choose == "主队(price1)":
        base += " AND price1 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    elif p_choose == "客队(price2)":
        base += " AND price2 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    base += f" ORDER BY {sc} {sw} LIMIT %s OFFSET %s "
    params = params + (ps, off)
    return pd.read_sql(base, engine, params=params)

@st.cache_data(ttl=30)
def get_all_data(sd, ed, ev, t1, t2, p_choose, pmi, pma):
    base = """
    SELECT * FROM nba_market_price
    WHERE time_utc BETWEEN %s AND %s
    AND event_title LIKE %s
    AND team1 LIKE %s
    AND team2 LIKE %s
    """
    params = (sd, ed, f"%{ev}%", f"%{t1}%", f"%{t2}%")
    if p_choose == "主队(price1)":
        base += " AND price1 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    elif p_choose == "客队(price2)":
        base += " AND price2 BETWEEN %s AND %s "
        params = params + (pmi, pma)
    base += " ORDER BY time_utc ASC "
    return pd.read_sql(base, engine, params=params)

# ========== 执行查询 ==========
total = 0
df = pd.DataFrame()
df_all = pd.DataFrame()

if search_btn:
    st.session_state.page = 1
total = get_total(start_dt, end_dt, event_key, t1_key, t2_key, price_choose, price_min, price_max)
df = get_data(start_dt, end_dt, event_key, t1_key, t2_key, price_choose, price_min, price_max,
              st.session_state.page, int(page_size), sort_col, sort_sql)
df_all = get_all_data(start_dt, end_dt, event_key, t1_key, t2_key, price_choose, price_min, price_max)
total_page = (total + int(page_size) -1) // int(page_size) if total > 0 else 1

# ========== 下载按钮 ==========
if not df_all.empty:
    csv_data = df_all.to_csv(index=False, encoding="utf-8-sig")
    download_placeholder.download_button(
        label="📥 下载全部查询数据",
        data=csv_data,
        file_name=f"NBA赛事数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
        type="secondary"
    )
else:
    download_placeholder.button("📥 下载全部查询数据", disabled=True, use_container_width=True, type="secondary")

# ========== 数据列表 ==========
st.subheader("📋 数据列表")
st.dataframe(df, use_container_width=True, hide_index=True)

# ========== 分页 ==========
if total > 0:
    col_prev, col_jump, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("上一页", disabled=(st.session_state.page <= 1), use_container_width=True):
            st.session_state.page -= 1
            st.rerun()
    with col_jump:
        col1, col2 = st.columns([1, 3])
        with col1:
            page_input = st.number_input(
                "跳转到", min_value=1, max_value=total_page, value=st.session_state.page, step=1, label_visibility="collapsed"
            )
            if page_input != st.session_state.page:
                st.session_state.page = int(page_input)
                st.rerun()
        with col2:
            st.markdown(f"""
            <div style="text-align: center; padding: 0.5rem; background-color: #e6f2ff; border-radius: 0.375rem;">
                第 {st.session_state.page} / {total_page} 页，共 {total} 条数据
            </div>
            """, unsafe_allow_html=True)
    with col_next:
        if st.button("下一页", disabled=(st.session_state.page >= total_page), use_container_width=True):
            st.session_state.page += 1
            st.rerun()

# ========== 赔率走势折线图（1分钟级） ==========
if not df_all.empty:
    st.subheader("📈 主客队 1 分钟级赔率走势")
    dfc = df_all.copy()
    dfc["time_utc"] = pd.to_datetime(dfc["time_utc"])
    dfc = dfc.sort_values("time_utc")
    
    # 1分钟聚合（核心修改点）
    dfc["time_1min"] = dfc["time_utc"].dt.floor("1min")
    dfc_1min = dfc.groupby("time_1min").last().reset_index()
    dfc_1min["time_1min"] = pd.to_datetime(dfc_1min["time_1min"])

    # 缺失值填充（适配你表的 decimal(6,4) 精度）
    dfc_1min["price1"] = dfc_1min["price1"].astype("Float64").ffill()
    dfc_1min["price2"] = dfc_1min["price2"].astype("Float64").ffill()
    
    # 自动获取队名
    home_team = dfc["team1"].iloc[0] if not dfc.empty else "主队"
    away_team = dfc["team2"].iloc[0] if not dfc.empty else "客队"
    dfc_1min = dfc_1min.rename(columns={"price1": home_team, "price2": away_team})

    # Y轴自适应
    price_min = dfc_1min[[home_team, away_team]].min().min()
    price_max = dfc_1min[[home_team, away_team]].max().max()
    y_min = max(0, price_min - 0.02)
    y_max = price_max + 0.02

    # 绘图
    chart = alt.Chart(dfc_1min).mark_line(strokeWidth=2).encode(
        x=alt.X("time_1min:T", title="时间（1分钟）"),
        y=alt.Y("value:Q", title="赔率", scale=alt.Scale(domain=[y_min, y_max])),
        color=alt.Color("key:N", title="球队", scale=alt.Scale(scheme="category10")),
        tooltip=[
    alt.Tooltip("time_1min:T", title="时间", format="%Y-%m-%d %H:%M"),
    alt.Tooltip("value:Q", title="赔率"),
    alt.Tooltip("key:N", title="球队")
]
    ).transform_fold(
        [home_team, away_team],
        as_=["key", "value"]
    ).properties(width="container", height=400)
    st.altair_chart(chart, use_container_width=True)
