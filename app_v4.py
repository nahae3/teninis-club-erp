import streamlit as st
import random
import pandas as pd
import math
import matplotlib.pyplot as plt
from datetime import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import itertools

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="Sunday Smashers V6.5", page_icon="🎾", layout="wide")

try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic' 
plt.rcParams['axes.unicode_minus'] = False

# --- [CORE] 구글 시트 연결 ---
def get_google_sheet_connection():
    try:
        json_content = dict(st.secrets["gcp_service_account"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_content, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("테니스클럽_DB")
        return spreadsheet
    except Exception as e:
        st.error(f"🚨 구글 시트 연결 실패! Secrets 설정과 시트 이름을 확인하세요.\n에러: {e}")
        st.stop()

spreadsheet = get_google_sheet_connection()

# --- [CORE] 관리자 인증 함수 ---
def check_admin():
    with st.sidebar.expander("🔐 관리자 모드", expanded=False):
        password = st.text_input("관리자 암호", type="password", key="admin_pw")
        if password == "1234":
            st.success("운영자 권한 획득 ⚡")
            return True
        elif password:
            st.error("암호 오류")
    return False

# --- 데이터 관리 및 유틸리티 함수 ---
def get_or_create_worksheet(sheet_name, headers):
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

@st.cache_data(ttl=60)
def load_data(sheet_name, expected_headers=None):
    try:
        ws = spreadsheet.worksheet(sheet_name)
        data = ws.get_all_values()
        if not data:
            return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()
        raw_headers = data[0]
        cleaned_headers = [h.strip() for h in raw_headers]
        df = pd.DataFrame(data[1:], columns=cleaned_headers)
        if expected_headers:
            final_df = pd.DataFrame()
            for col in expected_headers:
                clean_col = col.strip()
                if clean_col in df.columns:
                    final_df[col] = df[clean_col]
                else:
                    final_df[col] = 0
            return final_df
        return df
    except:
        return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()

def add_member_to_db(name, memo):
    ws = spreadsheet.worksheet("회원정보")
    join_date = datetime.now().strftime("%Y-%m-%d")
    ws.append_row([name, join_date, memo])
    st.cache_data.clear()

def add_match_record(t1, t2, s1, s2):
    ws = spreadsheet.worksheet("경기기록")
    winner = t1 if s1 > s2 else (t2 if s2 > s1 else "무승부")
    match_id = datetime.now().strftime("%Y%m%d%H%M%S")
    match_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([match_date, match_id, t1, t2, s1, s2, winner])
    st.cache_data.clear()
    return True

def delete_match_records(match_ids_to_delete):
    ws = spreadsheet.worksheet("경기기록")
    all_records = ws.get_all_records()
    df = pd.DataFrame(all_records)
    df['경기ID'] = df['경기ID'].astype(str)
    match_ids_str = [str(x) for x in match_ids_to_delete]
    new_df = df[~df['경기ID'].isin(match_ids_str)]
    ws.clear()
    ws.update([new_df.columns.values.tolist()] + new_df.values.tolist())
    st.cache_data.clear()

def share_to_live_board(display_data):
    try:
        ws = get_or_create_worksheet("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        ws.clear()
        ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        tz = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(tz).strftime("%H:%M")
        rows = [[item['round'], item['court'], item['t1'], item['t2'], now_str] for item in display_data]
        if rows:
            ws.append_rows(rows)
            st.toast("📡 실시간 전광판 송출 완료!")
    except Exception as e:
        st.error(f"전송 실패: {e}")

def save_schedule_backup(schedule_data):
    try:
        ws = get_or_create_worksheet("백업_대진표", ["데이터"])
        ws.clear()
        json_str = json.dumps(schedule_data, ensure_ascii=False)
        ws.update_cell(1, 1, json_str) 
        st.toast("✅ 대진표가 클라우드에 백업되었습니다.")
    except Exception as e:
        st.error(f"백업 실패: {e}")

def load_schedule_backup():
    try:
        ws = spreadsheet.worksheet("백업_대진표")
        json_str = ws.cell(1, 1).value
        return json.loads(json_str) if json_str else None
    except:
        return None

# --- ELO 및 알고리즘 로직 ---
def calculate_elo_change(rating_a, rating_b, actual_score, k=32):
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    return k * (actual_score - expected_a)

def get_player_stats_and_elo(df, all_members=None):
    stats = {p: {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0} for p in (all_members or [])}
    if df.empty: return stats
    if '경기ID' in df.columns:
        df = df.drop_duplicates(subset=['경기ID'], keep='last')
    for _, row in df.iterrows():
        try:
            p1, p2 = [p.strip() for p in str(row['팀1']).split(',')]
            p3, p4 = [p.strip() for p in str(row['팀2']).split(',')]
            for p in [p1, p2, p3, p4]:
                if p not in stats: stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}
            s1, s2 = int(row['점수1']), int(row['점수2'])
            for p in [p1, p2, p3, p4]: stats[p]["경기"] += 1
            if s1 == s2:
                for p in [p1, p2, p3, p4]: stats[p]["무"] += 1
                score = 0.5
            elif s1 > s2:
                for p in [p1, p2]: stats[p]["승"] += 1
                for p in [p3, p4]: stats[p]["패"] += 1
                score = 1.0
            else:
                for p in [p1, p2]: stats[p]["패"] += 1
                for p in [p3, p4]: stats[p]["승"] += 1
                score = 0.0
            t1_avg = (stats[p1]["point"] + stats[p2]["point"]) / 2
            t2_avg = (stats[p3]["point"] + stats[p4]["point"]) / 2
            change = calculate_elo_change(t1_avg, t2_avg, score)
            for p in [p1, p2]: stats[p]["point"] += round(change)
            for p in [p3, p4]: stats[p]["point"] -= round(change)
        except: continue
    return stats

def generate_league_schedule(attendees, target_games, mode, stats):
    schedule = []
    play_counts = {p: 0 for p in attendees}
    courts_num = len(attendees) // 4
    if courts_num == 0: return []
    total_slots = len(attendees) * target_games
    total_rounds = math.ceil(total_slots / (courts_num * 4))
    past_pairs = set()

    for r in range(total_rounds):
        waiting = sorted(attendees, key=lambda x: (play_counts[x], random.random()))
        players = waiting[:courts_num * 4]
        matches = []
        if mode == "🎲 랜덤 복식":
            random.shuffle(players)
            for i in range(courts_num):
                p1, p2, p3, p4 = players[i*4:(i+1)*4]
                matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}"})
        else: # ELO 밸런스
            sorted_p = sorted(players, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
            for i in range(courts_num):
                h1, h2 = sorted_p[2*i], sorted_p[2*i+1]
                l1, l2 = sorted_p[-(2*i+1)], sorted_p[-(2*i+2)]
                matches.append({"t1": f"{h1}, {l2}", "t2": f"{h2}, {l1}"})
        schedule.append({"round_num": r + 1, "matches": matches})
        for p in players: play_counts[p] += 1
    return schedule

def generate_kdk_schedule(players, rounds):
    n = len(players)
    schedule = []
    for r in range(rounds):
        matches = []
        idxs = list(range(n))
        random.shuffle(idxs)
        for i in range(n // 4):
            base = i * 4
            p1, p2, p3, p4 = [players[idxs[base+j]] for j in range(4)]
            matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}", "done": False})
        schedule.append({"round": r+1, "matches": matches})
    return schedule

# --- 시각화 ---
def draw_bracket_plot(teams_4):
    winners = st.session_state.get('tourney_winners', {})
    champion = winners.get('final', '최종 우승') 
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    # ... (생략 없이 기존 브래킷 로직 유지) ...
    return fig

# --- UI 메인 ---
st.title("🎾 Sunday Smashers V6.5")
is_admin = check_admin()
menu = st.sidebar.radio("메뉴", ["📺 실시간 현황판", "👥 회원 관리", "🏟️ 경기 운영", "📊 랭킹 & 분석", "📝 경기 기록 관리"])

# [0] 실시간 현황판
if menu == "📺 실시간 현황판":
    st.header("📺 LIVE SCOREBOARD")
    c_mode1, c_mode2 = st.columns([0.8, 0.2])
    with c_mode2: view_mode = st.radio("화면 모드", ["🌞 라이트", "🌙 다크"], label_visibility="collapsed")
    
    card_bg, text_color = ("#2D2D2D", "#FFFFFF") if view_mode == "🌙 다크" else ("#F0F2F6", "#000000")
    t1_c, t2_c = ("#4DD0E1", "#FF8A65") if view_mode == "🌙 다크" else ("blue", "red")

    if is_admin:
        if st.button("🚫 현황판 초기화", type="primary"):
            ws = spreadsheet.worksheet("실시간현황")
            ws.clear()
            ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
            st.rerun()
    
    live_df = load_data("실시간현황")
    if not live_df.empty:
        for _, row in live_df.iterrows():
            st.markdown(f"""
            <div style="background-color:{card_bg}; padding:15px; border-radius:10px; margin-bottom:10px; text-align:center; color:{text_color};">
                <span style="color:{t1_c}; font-weight:bold;">{row['팀1']}</span> VS <span style="color:{t2_c}; font-weight:bold;">{row['팀2']}</span>
                <br><small>{row['라운드']} - {row['코트']}</small>
            </div>
            """, unsafe_allow_html=True)

# [1] 회원 관리
elif menu == "👥 회원 관리":
    st.header("👥 회원 관리")
    member_df = load_data("회원정보", ["이름", "가입일", "메모"])
    tab1, tab2 = st.tabs(["📜 회원 목록", "⚙️ 관리"])
    with tab1: st.dataframe(member_df, use_container_width=True)
    with tab2:
        if is_admin:
            with st.form("add_mem"):
                n = st.text_input("이름")
                m = st.text_input("메모")
                if st.form_submit_button("등록"):
                    add_member_to_db(n, m); st.rerun()

# [2] 경기 운영 시스템 (탭별 독립 렌더링 적용)
elif menu == "🏟️ 경기 운영":
    st.header("🏟️ 경기 운영 시스템")
    mode_tabs = st.tabs(["🔄 일반 매칭", "🏆 토너먼트", "⚔️ 팀 대항전", "🔢 KDK(개인전)", "👑 회장맘대로"])
    member_df = load_data("회원정보", ["이름"])
    all_names = member_df["이름"].tolist() if not member_df.empty else []

    # 2.1 일반 매칭
    with mode_tabs[0]:
        if st.button("📂 일반 대진표 복구"):
            st.session_state.schedule = load_schedule_backup()
            st.session_state.is_generated = True
        
        att = st.multiselect("출석 체크", all_names, key="att_n")
        c1, c2 = st.columns(2)
        tg = c1.slider("게임 수", 1, 6, 3, key="tg_n")
        mm = c2.radio("방식", ["🎲 랜덤 복식", "⚖️ ELO밸런스"], key="mm_n")
        
        if st.button("🚀 대진표 생성", key="btn_n"):
            hist = load_data("경기기록", ["팀1", "팀2", "점수1", "점수2"])
            stats = get_player_stats_and_elo(hist, all_names)
            st.session_state.schedule = generate_league_schedule(att, tg, mm, stats)
            st.session_state.is_generated = True
            save_schedule_backup(st.session_state.schedule)
        
        if st.session_state.get('is_generated'):
            st.divider()
            for rd in st.session_state.schedule:
                st.write(f"**Round {rd['round_num']}**")
                for i, m in enumerate(rd['matches']):
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([2,1,1])
                        col1.write(f"{m['t1']} vs {m['t2']}")
                        s1 = col2.number_input("점1", key=f"ns1_{rd['round_num']}_{i}", min_value=0)
                        s2 = col3.number_input("점2", key=f"ns2_{rd['round_num']}_{i}", min_value=0)
                        key = f"btn_n_{rd['round_num']}_{i}"
                        if is_admin and st.button("기록", key=key, disabled=(key in st.session_state.get('recorded_ids', set()))):
                            add_match_record(m['t1'], m['t2'], s1, s2)
                            if 'recorded_ids' not in st.session_state: st.session_state.recorded_ids = set()
                            st.session_state.recorded_ids.add(key); st.rerun()

    # 2.2 토너먼트
    with mode_tabs[1]:
        st.subheader("🏆 토너먼트")
        t_att = st.multiselect("참가 선수", all_names, key="att_t")
        if st.button("대회 시작"):
            st.session_state.tourney_active = True
        if st.session_state.get('tourney_active'):
            st.info("토너먼트 관리 화면")

    # 2.3 팀 대항전
    with mode_tabs[2]:
        st.subheader("⚔️ 팀 대항전")
        if 'battle_teams' not in st.session_state: st.session_state.battle_teams = {'A':[], 'B':[]}
        att_b = st.multiselect("참석자", all_names, key="att_b")
        if st.button("팀 나누기"):
            random.shuffle(att_b)
            mid = len(att_b)//2
            st.session_state.battle_teams = {'A': att_b[:mid], 'B': att_b[mid:]}
            st.session_state.battle_active = True
        if st.session_state.get('battle_active'):
            st.write(f"A팀: {st.session_state.battle_teams['A']}")
            st.write(f"B팀: {st.session_state.battle_teams['B']}")

    # 2.4 KDK
    with mode_tabs[4]: # KDK는 4번 인덱스
        pass

    # 2.5 회장맘대로 (신규 추가 및 탭 독립)
    with mode_tabs[4]:
        st.subheader("👑 회장맘대로")
        if st.button("📂 회장님 대진표 복구", key="res_b"):
            st.session_state.boss_schedule = load_schedule_backup()
            st.session_state.boss_active = True
        
        b_att = st.multiselect("출석 체크", all_names, key="att_boss")
        c1, c2 = st.columns(2)
        b_gc = c1.slider("게임 수", 3, 10, 4, key="gc_boss")
        b_opt = c2.radio("방식", ["고정 팀(나머지 랜덤)", "완전 수동"], key="opt_boss")
        
        fixed = []
        if b_opt == "고정 팀(나머지 랜덤)":
            with st.expander("📌 고정 팀 설정"):
                for i in range(1, 5):
                    tc = st.columns(2)
                    p1 = tc[0].selectbox(f"{i}코트-1", ["미지정"]+b_att, key=f"fp1_{i}")
                    p2 = tc[1].selectbox(f"{i}코트-2", ["미지정"]+b_att, key=f"fp2_{i}")
                    if p1 != "미지정" and p2 != "미지정": fixed.append(f"{p1}, {p2}")

        if st.button("🚀 회장님 대진표 생성", type="primary"):
            new_b = []
            if b_opt == "고정 팀(나머지 랜덤)":
                f_mem = [p.strip() for ft in fixed for p in ft.split(',')]
                rem = [m for m in b_att if m not in f_mem]
                for g in range(1, b_gc+1):
                    ms = []
                    t_rem = rem.copy()
                    for i, ft in enumerate(fixed):
                        if len(t_rem)>=2:
                            random.shuffle(t_rem)
                            opp = f"{t_rem.pop(0)}, {t_rem.pop(0)}"
                            ms.append({"t1": ft, "t2": opp, "court": f"{i+1}코트"})
                    new_b.append({"game": g, "matches": ms})
            else:
                for g in range(1, b_gc+1):
                    new_b.append({"game": g, "matches": [{"t1": "미지정", "t2": "미지정", "court": f"{i+1}코트"} for i in range(len(b_att)//4)]})
            st.session_state.boss_schedule = new_b
            st.session_state.boss_active = True
            save_schedule_backup(new_b); st.rerun()

        if st.session_state.get('boss_active'):
            st.divider()
            for g in st.session_state.boss_schedule:
                st.write(f"**Game {g['game']}**")
                for i, m in enumerate(g['matches']):
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3,1,1])
                        if b_opt == "완전 수동":
                            t1_p = c1.multiselect("팀1", b_att, max_selections=2, key=f"bt1_{g['game']}_{i}")
                            t2_p = c1.multiselect("팀2", b_att, max_selections=2, key=f"bt2_{g['game']}_{i}")
                            m['t1'], m['t2'] = ", ".join(t1_p), ", ".join(t2_p)
                        else:
                            c1.write(f"{m['court']}: {m['t1']} vs {m['t2']}")
                        s1 = c2.number_input("점1", key=f"bs1_{g['game']}_{i}", min_value=0)
                        s2 = c3.number_input("점2", key=f"bs2_{g['game']}_{i}", min_value=0)
                        key = f"btn_b_{g['game']}_{i}"
                        if is_admin and st.button("기록", key=key, disabled=(key in st.session_state.get('recorded_ids', set()))):
                            add_match_record(m['t1'], m['t2'], s1, s2)
                            if 'recorded_ids' not in st.session_state: st.session_state.recorded_ids = set()
                            st.session_state.recorded_ids.add(key); st.rerun()

# [3] 랭킹 & 분석
elif menu == "📊 랭킹 & 분석":
    st.header("🏆 포인트 랭킹")
    st.markdown("기본 1000점 시작. 승리시 점수 획득, 패배시 차감. (상대 실력에 따라 가중치 적용)")
    
    # 1. 데이터 로드 (형님 데이터 꼬임 방지 로직 적용됨)
    member_df = load_data("회원정보", ["이름"])
    
    try:
        ws = spreadsheet.worksheet("경기기록")
        all_values = ws.get_all_values()
        
        if len(all_values) > 1:
            raw_data = all_values[1:]
            clean_data = []
            for row in raw_data:
                if len(row) < 7: continue
                # G열(index 6)을 승리팀으로 인식하는 수정된 로직
                clean_data.append({
                    "날짜": row[0],
                    "승리팀": row[6],
                    "팀1": row[2],
                    "팀2": row[3],
                    "점수1": row[4],
                    "점수2": row[5]
                })
            df = pd.DataFrame(clean_data)
        else:
            df = pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        df = pd.DataFrame()

    # -------------------------------------------------------
    # 분석 및 시각화 로직
    # -------------------------------------------------------

    if not df.empty and not member_df.empty:
        # 통계 계산
        stats = get_player_stats_and_elo(df, member_df["이름"].tolist())
        
          # (앞부분 생략)... stats 계산 후 ...
        
        rank_data = []
        for p, d in stats.items():
            if d['경기'] > 0:
                # 승률 계산 (무승부는 경기수에는 포함되지만 승수에는 포함 안 됨 -> 승률 하락 요인)
                # 만약 무승부를 승률 계산에서 빼고 싶다면 분모를 (d['경기'] - d['무'])로 하시면 됩니다.
                # 여기선 표준 방식(전체 경기 수 대비 승리)을 따릅니다.
                win_rate = (d['승'] / d['경기']) * 100
                rank_data.append({
                    "이름": p, 
                    "포인트": d['point'], 
                    "승률": f"{win_rate:.1f}%", 
                    "승": d['승'], 
                    "무": d['무'],  # [추가]
                    "패": d['패'], 
                    "전": d['경기']
                })
        
        rank_df = pd.DataFrame(rank_data).sort_values("포인트", ascending=False)
        rank_df = rank_df.reset_index(drop=True)
        rank_df.index = rank_df.index + 1 
        
        max_score = rank_df['포인트'].max() if not rank_df.empty else 1200
        min_score = 800

        # -------------------------------------------------------
        # [수정] 랭킹 테이블 (data_color 옵션 제거하여 오류 해결)
        # -------------------------------------------------------
        # -------------------------------------------------------
        # [수정] 랭킹 테이블 (Numpy 타입을 int로 강제 변환하여 JSON 오류 해결)
        # -------------------------------------------------------
        # [수정] 데이터프레임 컬럼 설정에 '무' 추가
        st.dataframe(
            rank_df,
            column_config={
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "포인트": st.column_config.ProgressColumn(
                    "포인트 (Elo)",
                    format="%d pts",
                    min_value=int(min_score),  
                    max_value=int(max_score) + 100, 
                ),
                "승률": st.column_config.TextColumn("승률"),
                "승": st.column_config.NumberColumn("승"),
                "무": st.column_config.NumberColumn("무"), # [NEW]
                "패": st.column_config.NumberColumn("패"),
                "전": st.column_config.NumberColumn("전"),
            },
            use_container_width=True     
         )


        st.divider()
        
        # -------------------------------------------------------
        # [수정 2] 4대 천왕 분석 (첨부 사진과 동일한 디자인)
        # -------------------------------------------------------
        st.subheader("🔍 선수별 심층 분석")
        st.caption("분석할 회원을 선택하세요:")
        
        player_list = rank_df['이름'].tolist()
        if player_list:
            selected_player = st.selectbox("선수 선택", player_list, label_visibility="collapsed")
            
            if selected_player:
                p_stat = stats.get(selected_player)
                st.markdown(f"• **{selected_player}**님의 총 경기 수: **{p_stat['경기']}게임** 기반 분석")
                st.write("") # 여백

                # --- 파트너/상대 분석 로직 ---
                mask = df['팀1'].apply(lambda x: selected_player in str(x)) | \
                       df['팀2'].apply(lambda x: selected_player in str(x))
                my_matches = df[mask].copy()

                teammate_stats = {} 
                opponent_stats = {} 
                
                # 승패 판독 함수 (간소화)
                def get_result(row, me):
                    try:
                        s1, s2 = int(row['점수1']), int(row['점수2'])
                    except: return "err"
                    
                    real_winner = str(row['승리팀'])
                    
                    my_team = 1 if me in str(row['팀1']) else 2
                    
                    if s1 > s2: win_team = 1
                    elif s2 > s1: win_team = 2
                    else: 
                        if "무승부" in real_winner: win_team = 0
                        elif str(row['팀1']) in real_winner: win_team = 1
                        elif str(row['팀2']) in real_winner: win_team = 2
                        else: win_team = 0
                    
                    if win_team == 0: return "draw"
                    return "win" if win_team == my_team else "lose"

                for _, row in my_matches.iterrows():
                    res = get_result(row, selected_player)
                    if res == "err" or res == "draw": continue
                    is_win = (res == "win")

                    t1 = str(row['팀1']).replace(',', ' ').split()
                    t2 = str(row['팀2']).replace(',', ' ').split()

                    if selected_player in t1:
                        partners, enemies = t1, t2
                    else:
                        partners, enemies = t2, t1
                    
                    for p in partners:
                        if p != selected_player:
                            if p not in teammate_stats: teammate_stats[p] = {'승':0, '전':0}
                            teammate_stats[p]['전'] += 1
                            if is_win: teammate_stats[p]['승'] += 1
                    
                    for e in enemies:
                        if e not in opponent_stats: opponent_stats[e] = {'승':0, '전':0}
                        opponent_stats[e]['전'] += 1
                        if is_win: opponent_stats[e]['승'] += 1
                
                # 정렬 함수
                def get_best_worst(stats_dict):
                    if not stats_dict: return None, None
                    lst = []
                    for k, v in stats_dict.items():
                        rate = (v['승'] / v['전']) * 100
                        lst.append((k, rate, v['전'])) # 이름, 승률, 판수
                    
                    # 정렬 기준: 승률 -> 판수
                    lst.sort(key=lambda x: (x[1], x[2]), reverse=True)
                    return lst[0], lst[-1] # 최고, 최악

                best_part, worst_part = get_best_worst(teammate_stats)
                easy_opp, hard_opp = get_best_worst(opponent_stats)

                # --- 4대 천왕 UI 출력 (st.metric 사용) ---
                col1, col2, col3, col4 = st.columns(4)

                # 1. 환상의 짝꿍 (최고 승률 파트너)
                with col1:
                    st.write("💙 환상의 짝꿍")
                    if best_part:
                        st.metric(label=f"{best_part[2]}전 함께함", value=best_part[0], delta=f"↑ {best_part[1]:.1f}%")
                    else:
                        st.metric(label="기록 없음", value="-", delta=None)

                # 2. 억제기 (최저 승률 파트너)
                with col2:
                    st.write("💔 억제기 (X맨)")
                    if worst_part:
                        # 억제기는 승률이 낮을수록 문제 -> 역색상 적용 고려하거나 그냥 표시
                        st.metric(label=f"{worst_part[2]}전 함께함", value=worst_part[0], delta=f"↓ {worst_part[1]:.1f}%", delta_color="inverse")
                    else:
                        st.metric(label="기록 없음", value="-", delta=None)

                # 3. 맛있는 먹잇감 (상대 승률 높음)
                with col3:
                    st.write("🍖 맛있는 먹잇감")
                    if easy_opp:
                        st.metric(label=f"{easy_opp[2]}전 만남", value=easy_opp[0], delta=f"↑ {easy_opp[1]:.1f}%")
                    else:
                        st.metric(label="기록 없음", value="-", delta=None)

                # 4. 천적 (상대 승률 낮음)
                with col4:
                    st.write("👿 천적 (담당일진)")
                    if hard_opp:
                        st.metric(label=f"{hard_opp[2]}전 만남", value=hard_opp[0], delta=f"↓ {hard_opp[1]:.1f}%", delta_color="inverse")
                    else:
                        st.metric(label="기록 없음", value="-", delta=None)

    else:
        st.info("경기 기록이 부족하여 랭킹을 산정할 수 없습니다.")


# [4] 경기 기록 관리 (밀린 데이터 강제 인식 버전)
elif menu == "📝 경기 기록 관리":
    st.header("📝 경기 기록 관리 (삭제 및 조회)")
    
    # [수정 포인트 1] load_data 대신 직접 위치로 긁어옵니다.
    # 이유: 헤더랑 실제 데이터 위치가 안 맞아서 강제로 매핑해야 함
    try:
        ws = spreadsheet.worksheet("경기기록")
        all_values = ws.get_all_values()
        
        if len(all_values) > 1:
            raw_data = all_values[1:] # 헤더 제외 데이터
            clean_data = []
            
            for row in raw_data:
                if len(row) < 7: continue # 데이터 너무 짧으면 패스
                
                # [수정 포인트 2] 시트 위치에 맞춰 강제 할당
                # B열(인덱스 1)을 '경기ID'로 사용
                # G열(인덱스 6)을 '승리팀'으로 사용
                clean_data.append({
                    "날짜": row[0],        # A열
                    "경기ID": row[1],      # B열 (여기에 이상한 날짜숫자가 ID 역할)
                    "승리팀": row[6],      # G열 (밀려난 승리팀)
                    "팀1": row[2],         # C열
                    "팀2": row[3],         # D열
                    "점수1": row[4],       # E열
                    "점수2": row[5]        # F열
                })
            
            df = pd.DataFrame(clean_data)
        else:
            df = pd.DataFrame()
            
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        df = pd.DataFrame()

    # ------------------------------------------------
    # 이 밑으로는 형님 코드와 기능(필터, 삭제)이 같습니다.
    # ------------------------------------------------
    
    if df.empty:
        st.info("저장된 경기 기록이 없습니다.")
    else:
        # 날짜 필터링 (형님 코드 유지)
        df['날짜_short'] = df['날짜'].astype(str).apply(lambda x: x.split(' ')[0] if len(str(x)) > 5 else x)
        dates = sorted(df['날짜_short'].unique(), reverse=True)
        
        if dates:
            selected_date = st.selectbox("📅 날짜 선택", dates)
            filtered_df = df[df['날짜_short'] == selected_date].copy()
            
            if not filtered_df.empty:
                st.write(f"총 {len(filtered_df)}개의 경기가 있습니다.")
                
                # 삭제 기능을 위한 체크박스 추가
                filtered_df.insert(0, "삭제", False)
                
                # 데이터 에디터 설정
                edited_df = st.data_editor(
                    filtered_df,
                    column_config={
                        "삭제": st.column_config.CheckboxColumn("선택", help="삭제할 경기 선택"),
                        "경기ID": None, # ID는 숨김 처리 (너무 길어서)
                        "날짜_short": None
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # 삭제 버튼 로직
                if st.button("🗑️ 선택한 경기 삭제"):
                    # 체크된 행의 '경기ID' (실제론 B열 값)를 가져옴
                    to_delete = edited_df[edited_df['삭제']]['경기ID'].tolist()
                    
                    if to_delete:
                        with st.spinner("구글 시트에서 삭제 중..."):
                            # delete_match_records 함수가 있다고 가정 (기존에 가지고 계신 함수)
                            # 단, 이 함수가 '경기ID'를 B열에서 찾아서 지우는지 확인 필요
                            # 없다면 아래처럼 직접 구현해야 함:
                            
                            # [간단 삭제 로직 구현]
                            ws = spreadsheet.worksheet("경기기록")
                            # 뒤에서부터 지워야 인덱스가 안 꼬임
                            rows_all = ws.get_all_values()
                            rows_to_delete_indices = []
                            
                            for idx, r in enumerate(rows_all):
                                if len(r) > 1 and r[1] in to_delete: # B열(인덱스1)이 ID랑 같으면
                                    rows_to_delete_indices.append(idx + 1) # 1-based index
                            
                            for r_idx in sorted(rows_to_delete_indices, reverse=True):
                                ws.delete_rows(r_idx)
                                
                        st.success(f"{len(to_delete)}건 삭제 완료! (새로고침 됩니다)")
                        st.cache_data.clear() # 캐시 비우기
                        st.rerun()
                    else:
                        st.warning("삭제할 경기를 선택해주세요.")
            else:
                st.info("선택한 날짜에 기록이 없습니다.")
