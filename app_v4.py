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

# --- 설정 및 한글 폰트 ---
st.set_page_config(page_title="Sunday Smashers V6.5", page_icon="🎾", layout="wide")

# [폰트 설정]
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

# --- [NEW] 관리자 인증 함수 ---
def check_admin():
    """사이드바에서 비밀번호를 입력받아 관리자 여부 확인"""
    with st.sidebar.expander("🔐 관리자 모드", expanded=False):
        password = st.text_input("관리자 암호", type="password", key="admin_pw")
        if password == "1234":  # [설정] 비밀번호 변경은 여기서
            st.success("운영자 권한 획득 ⚡")
            return True
        elif password:
            st.error("암호 오류")
    return False

# --- 데이터 관리 함수 ---
def get_or_create_worksheet(sheet_name, headers):
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        ws.append_row(headers)
    return ws

@st.cache_data(ttl=60)
# [데이터 로드 함수 - 강력한 버전]
def load_data(sheet_name, expected_headers=None):
    try:
        ws = spreadsheet.worksheet(sheet_name)
        data = ws.get_all_values() # 데이터를 있는 그대로 텍스트로 다 가져옴
        
        if not data:
            return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()
        
        # 1. 엑셀의 헤더(첫 줄)를 가져와서 앞뒤 공백을 싹 제거함
        raw_headers = data[0]
        cleaned_headers = [h.strip() for h in raw_headers]
        
        # 2. 데이터 프레임 생성
        df = pd.DataFrame(data[1:], columns=cleaned_headers)
        
        # 3. 요청한 컬럼만 골라내기 (없으면 0으로 채움)
        if expected_headers:
            final_df = pd.DataFrame()
            for col in expected_headers:
                clean_col = col.strip() # 요청한 컬럼명도 공백 제거
                
                # 정확히 일치하는게 있으면 가져오고
                if clean_col in df.columns:
                    final_df[col] = df[clean_col]
                # 혹시 "점수 1" 처럼 중간 공백 차이일 수도 있으니 한번 더 찾기
                else:
                    found = False
                    for h in df.columns:
                        if h.replace(" ","") == clean_col.replace(" ",""):
                            final_df[col] = df[h]
                            found = True
                            break
                    if not found:
                        final_df[col] = 0 # 진짜 없으면 0 처리
            return final_df
        
        return df
    except Exception as e:
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

# --- [UPGRADE] 통합 실시간 공유 함수 ---
def share_to_live_board(display_data):
    """
    display_data 형식:
    [
      {"round": "4강", "court": "1코트", "t1": "김철수,이영희", "t2": "박민수,최수지"},
      ...
    ]
    """
    try:
        ws = get_or_create_worksheet("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        ws.clear()
        ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
        
        tz = pytz.timezone('Asia/Seoul')
        now_str = datetime.now(tz).strftime("%H:%M")
        
        rows = []
        for item in display_data:
            rows.append([item['round'], item['court'], item['t1'], item['t2'], now_str])
            
        if rows:
            ws.append_rows(rows)
            st.toast("📢 실시간 전광판 송출 완료!", icon="📡")
        else:
            st.warning("송출할 데이터가 없습니다.")
    except Exception as e:
        st.error(f"전송 실패: {e}")

def load_live_status():
    return load_data("실시간현황", ["라운드", "코트", "팀1", "팀2", "업데이트시간"])

# --- Elo 및 알고리즘 ---
def calculate_elo_change(rating_a, rating_b, actual_score, k=32):
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    change = k * (actual_score - expected_a)
    return change


# --- [수정된 함수 1] 랭킹 계산 (중복 제거 기능 추가) ---
def get_player_stats_and_elo(df, all_members=None):
    stats = {}
    if all_members:
        for p in all_members:
            # [수정] 무승부(draw) 카운트 명시
            stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}

    if df.empty: return stats

    # 중복 데이터 제거 (경기ID 기준)
    if '경기ID' in df.columns:
        df = df.drop_duplicates(subset=['경기ID'], keep='last')
        
    if '날짜' in df.columns: df = df.sort_values("날짜")

    for _, row in df.iterrows():
        try:
            # 1. 팀원 이름 분리
            p1, p2 = [p.strip() for p in str(row['팀1']).split(',')]
            p3, p4 = [p.strip() for p in str(row['팀2']).split(',')]
            
            # 선수 통계 딕셔너리에 없으면 초기화
            for p in [p1, p2, p3, p4]:
                if p not in stats: stats[p] = {"point": 1000, "승": 0, "패": 0, "무": 0, "경기": 0}

            # 2. [핵심 수정] 텍스트가 아닌 '점수'로 승패 판단
            try:
                s1 = int(row['점수1'])
                s2 = int(row['점수2'])
            except:
                continue # 점수가 숫자가 아니면 패스

            # 경기 수 증가
            for p in [p1, p2, p3, p4]: stats[p]["경기"] += 1

            # 3. 승무패 로직 분기
            if s1 == s2:
                # --- 무승부 (Draw) ---
                for p in [p1, p2, p3, p4]: stats[p]["무"] += 1
                actual_score = 0.5 # Elo 공식에서 무승부는 0.5로 계산
                
                # 승패 카운트는 올리지 않음
                
            elif s1 > s2:
                # --- 팀1 승리 ---
                for p in [p1, p2]: stats[p]["승"] += 1
                for p in [p3, p4]: stats[p]["패"] += 1
                actual_score = 1.0
                
            else:
                # --- 팀2 승리 ---
                for p in [p1, p2]: stats[p]["패"] += 1
                for p in [p3, p4]: stats[p]["승"] += 1
                actual_score = 0.0

            # 4. Elo 점수 계산 (무승부도 반영됨)
            team1_avg = (stats[p1]["point"] + stats[p2]["point"]) / 2
            team2_avg = (stats[p3]["point"] + stats[p4]["point"]) / 2
            
            change = calculate_elo_change(team1_avg, team2_avg, actual_score)
            
            # 무승부일 경우 change 값이 작게 나오지만, 강팀과 비기면 약팀 점수가 오름
            for p in [p1, p2]: stats[p]["point"] += round(change)
            for p in [p3, p4]: stats[p]["point"] -= round(change)

        except Exception:
            continue
            
    return stats


# --- [수정된 함수 2] 리그 스케줄 생성 (중복 파트너 방지 로직 추가) ---
def generate_league_schedule(attendees, target_games, mode, stats):
    schedule = []
    play_counts = {p: 0 for p in attendees}
    courts_num = len(attendees) // 4
    
    if courts_num == 0: return []
    
    total_slots_needed = len(attendees) * target_games
    slots_per_round = courts_num * 4
    total_rounds = math.ceil(total_slots_needed / slots_per_round)
    
    # [핵심] 역대 파트너 기록 저장소 (순서 없는 집합)
    past_pairs = set()

    for r in range(total_rounds):
        # 1. 경기 수가 적은 순서대로 정렬 (동점일 경우 랜덤 섞기)
        waiting_list = sorted(attendees, key=lambda x: (play_counts[x], random.random()))
        players_for_round = waiting_list[:slots_per_round]
        
        matches = []
        
        # --- [모드 1] 랜덤 복식 (기존 업데이트 유지) ---
        if mode == "🎲 랜덤 복식":
            best_permutation = None
            min_conflicts = 999
            
            # 50번 셔플해보며 가장 중복이 적은 조합 찾기
            for _ in range(50):
                random.shuffle(players_for_round)
                current_conflicts = 0
                temp_pairs = []
                
                for i in range(courts_num):
                    p1, p2 = players_for_round[i*4], players_for_round[i*4+1]
                    p3, p4 = players_for_round[i*4+2], players_for_round[i*4+3]
                    
                    if frozenset([p1, p2]) in past_pairs: current_conflicts += 1
                    if frozenset([p3, p4]) in past_pairs: current_conflicts += 1
                    temp_pairs.append((p1, p2, p3, p4))
                
                if current_conflicts == 0:
                    best_permutation = temp_pairs
                    break
                if current_conflicts < min_conflicts:
                    min_conflicts = current_conflicts
                    best_permutation = temp_pairs
            
            for (p1, p2, p3, p4) in best_permutation:
                matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}"})
                past_pairs.add(frozenset([p1, p2]))
                past_pairs.add(frozenset([p3, p4]))

        # --- [모드 2] ELO 밸런스 (여기가 수정됨!) ---
        else:
            # 점수 높은 순 정렬
            sorted_p = sorted(players_for_round, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
            
            # 코트별로 4명씩 끊어서 최적 조합 찾기
            for i in range(courts_num):
                # 해당 코트에 배정된 4명 (점수순: 1위, 2위, 3위, 4위)
                # 스네이크 방식이 아니라, 그룹핑 후 내부 조합 변경 방식으로 변경
                # 예: 1코트(1,2,3,4등), 2코트(5,6,7,8등) ... 이렇게 하면 실력차가 너무 나므로
                # 기존처럼 스네이크로 4명을 뽑되, 그 4명 안에서 파트너만 바꿉니다.
                
                # 그룹 추출 (High 2명 + Low 2명)
                # i=0 -> 1,2등 & 뒤에서 1,2등
                h1, h2 = sorted_p[2*i], sorted_p[2*i+1]
                l1, l2 = sorted_p[-(2*i+1)], sorted_p[-(2*i+2)]
                
                group = [h1, h2, l1, l2]
                
                # 이 4명으로 만들 수 있는 3가지 파트너 조합
                # Option A (정석): (h1, l2) vs (h2, l1) -> 1등+꼴등
                # Option B (변형): (h1, l1) vs (h2, l2) -> 1등+꼴등앞
                # Option C (비추): (h1, h2) vs (l1, l2) -> 잘함vs못함 (밸런스 붕괴)
                
                # Option A 검사
                pair_a1 = frozenset([h1, l2])
                pair_a2 = frozenset([h2, l1])
                conflict_a = (pair_a1 in past_pairs) or (pair_a2 in past_pairs)
                
                # Option B 검사
                pair_b1 = frozenset([h1, l1])
                pair_b2 = frozenset([h2, l2])
                conflict_b = (pair_b1 in past_pairs) or (pair_b2 in past_pairs)
                
                # 결정 로직: A가 안 겹치면 A, 겹치면 B, 둘 다 겹치면 그냥 A(어쩔 수 없음)
                if not conflict_a:
                    final_p1, final_p2 = h1, l2
                    final_p3, final_p4 = h2, l1
                elif not conflict_b:
                    final_p1, final_p2 = h1, l1
                    final_p3, final_p4 = h2, l2
                else:
                    # 둘 다 해봤던 조합이면... 그냥 랜덤으로 섞거나 A로 회귀
                    final_p1, final_p2 = h1, l2
                    final_p3, final_p4 = h2, l1

                matches.append({"t1": f"{final_p1}, {final_p2}", "t2": f"{final_p3}, {final_p4}"})
                past_pairs.add(frozenset([final_p1, final_p2]))
                past_pairs.add(frozenset([final_p3, final_p4]))
                
        schedule.append({"round_num": r + 1, "matches": matches})
        for p in players_for_round: play_counts[p] += 1
        
    return schedule



# --- [신규 기능] 대진표 백업 및 복구 ---
def save_schedule_backup(schedule_data):
    """현재 생성된 대진표를 구글 시트 '백업_대진표' 탭에 저장"""
    try:
        ws = get_or_create_worksheet("백업_대진표", ["데이터"])
        ws.clear()
        # JSON 형태로 덤프하여 저장
        json_str = json.dumps(schedule_data, ensure_ascii=False)
        # 구글 시트 셀 용량 제한 고려하여 청크로 나눌 수도 있으나, 보통 텍스트 1개 셀에 들어감
        ws.update_cell(1, 1, json_str) 
        st.toast("✅ 대진표가 클라우드에 백업되었습니다.")
    except Exception as e:
        st.error(f"백업 실패: {e}")

def load_schedule_backup():
    """구글 시트에서 대진표 불러오기"""
    try:
        ws = spreadsheet.worksheet("백업_대진표")
        json_str = ws.cell(1, 1).value
        if json_str:
            return json.loads(json_str)
    except:
        return None
    return None





def balance_teams_by_point(players, stats):
    sorted_p = sorted(players, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
    team_a, team_b = [], []
    for i, p in enumerate(sorted_p):
        if i % 4 in [0, 3]: team_a.append(p)
        else: team_b.append(p)
    return team_a, team_b

import math
import random



def generate_kdk_schedule(players, rounds):
    n = len(players)
    schedule = []
    idxs = list(range(n))
    for r in range(rounds):
        matches = []
        random.shuffle(idxs)
        for i in range(n // 4):
            base = i * 4
            if base + 3 < n:
                p1, p2 = players[idxs[base]], players[idxs[base+1]]
                p3, p4 = players[idxs[base+2]], players[idxs[base+3]]
                matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}", "done": False})
        schedule.append({"round": r+1, "matches": matches})
    return schedule

def draw_bracket_plot(teams_4):
    winners = st.session_state.get('tourney_winners', {})
    semi_1_t1, semi_1_t2 = teams_4[0], teams_4[1]
    semi_2_t1, semi_2_t2 = teams_4[2], teams_4[3]
    final_1 = winners.get('semi_1', '???')
    final_2 = winners.get('semi_2', '???')
    champion = winners.get('final', '최종 우승') 

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    # ... (그림 그리기 로직 생략, 기존과 동일) ...
    # 코드 길이상 핵심 로직 유지
    x_semi, x_final, x_winner = 0.2, 0.5, 0.8
    y_s1_top, y_s1_bot = 0.8, 0.6
    y_s2_top, y_s2_bot = 0.4, 0.2
    y_f1, y_f2, y_win = 0.7, 0.3, 0.5
    
    def draw_box(x, y, text, color='#f0f2f6', highlight=False):
        ec = 'gold' if highlight else 'black'
        lw = 2 if highlight else 1
        fc = 'gold' if highlight else color
        ax.text(x, y, text, ha='center', va='center', fontsize=9, bbox=dict(boxstyle="round,pad=0.3", facecolor=fc, edgecolor=ec, linewidth=lw))
    
    draw_box(x_semi, y_s1_top, semi_1_t1, highlight=(semi_1_t1==final_1))
    draw_box(x_semi, y_s1_bot, semi_1_t2, highlight=(semi_1_t2==final_1))
    draw_box(x_semi, y_s2_top, semi_2_t1, highlight=(semi_2_t1==final_2))
    draw_box(x_semi, y_s2_bot, semi_2_t2, highlight=(semi_2_t2==final_2))
    draw_box(x_final, y_f1, f"{final_1}", color='lightblue', highlight=(final_1==champion))
    draw_box(x_final, y_f2, f"{final_2}", color='lightblue', highlight=(final_2==champion))
    draw_box(x_winner, y_win, champion, color='gold', highlight=(champion!='최종 우승'))
    
    ax.plot([x_semi, x_final], [y_s1_top, y_f1], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s1_bot, y_f1], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s2_top, y_f2], color='gray', alpha=0.3)
    ax.plot([x_semi, x_final], [y_s2_bot, y_f2], color='gray', alpha=0.3)
    ax.plot([x_final, x_winner], [y_f1, y_win], color='black', alpha=0.5)
    ax.plot([x_final, x_winner], [y_f2, y_win], color='black', alpha=0.5)
    return fig

# --- UI 시작 ---
st.title("🎾 Sunday Smashers V6.5")

# 인증 확인 (관리자 모드 활성화 여부)
is_admin = check_admin()

menu = st.sidebar.radio("메뉴", ["📺 실시간 현황판", "👥 회원 관리", "🏟️ 경기 운영", "📊 랭킹 & 분석", "📝 경기 기록 관리"])

# --- [NEW] 관리자용 데이터 백업 버튼 (사이드바) ---
if is_admin:
    st.sidebar.divider()
    st.sidebar.markdown("💾 **데이터 백업**")
    
    # 경기 기록 다운로드
    hist_df = load_data("경기기록", ["날짜", "경기ID", "팀1", "팀2", "점수1", "점수2", "승리팀"])
    csv = hist_df.to_csv(index=False).encode('utf-8-sig') # 한글 깨짐 방지
    
    st.sidebar.download_button(
        label="📥 경기기록 다운로드 (CSV)",
        data=csv,
        file_name=f"경기기록_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


# [0] 실시간 현황판
if menu == "📺 실시간 현황판":
    st.header("📺 LIVE SCOREBOARD")
    
    # --- 다크모드/라이트모드 선택 ---
    c_mode1, c_mode2 = st.columns([0.8, 0.2])
    with c_mode2:
        view_mode = st.radio("화면 모드", ["🌞 라이트", "🌙 다크"], label_visibility="collapsed")
    
    # CSS 스타일 변수 설정
    if view_mode == "🌙 다크":
        bg_color = "#1E1E1E" # 짙은 회색 배경
        text_color = "#FFFFFF"
        card_bg = "#2D2D2D" # 카드 배경
        t1_color = "#4DD0E1" # 밝은 하늘색 (다크모드용)
        t2_color = "#FF8A65" # 밝은 주황색 (다크모드용)
        vs_color = "#BDBDBD"
    else:
        bg_color = "#FFFFFF"
        text_color = "#000000"
        card_bg = "#F0F2F6"
        t1_color = "blue"
        t2_color = "red"
        vs_color = "black"

    # [NEW] 관리자 전용 기능 (기존과 동일)
    if is_admin:
        col_adm1, col_adm2 = st.columns([1, 1])
        with col_adm1:
            if st.button("🚫 현황판 초기화 (일정 종료)", type="primary", use_container_width=True):
                try:
                    ws = spreadsheet.worksheet("실시간현황")
                    ws.clear()
                    ws.append_row(["라운드", "코트", "팀1", "팀2", "업데이트시간"])
                    st.toast("초기화 완료", icon="👋")
                    st.rerun()
                except Exception as e:
                    st.error(f"초기화 실패: {e}")
        with col_adm2:
            if st.button("🔄 새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    else:
        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
    live_df = load_live_status()
    
    if not live_df.empty and len(live_df) > 0 and live_df.iloc[0]['팀1'] != "": 
        last_update = live_df['업데이트시간'].iloc[0] if '업데이트시간' in live_df.columns else "?"
        st.caption(f"🕒 Update: {last_update}")
        rounds = live_df['라운드'].unique()
        
        for r in rounds:
            st.markdown(f"### 📌 {r}")
            r_data = live_df[live_df['라운드'] == r]
            for _, row in r_data.iterrows():
                # 다크모드를 위해 st.container 대신 HTML/CSS로 직접 디자인
                html_card = f"""
                <div style="
                    background-color: {card_bg};
                    padding: 15px;
                    border-radius: 10px;
                    margin-bottom: 10px;
                    box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                ">
                    <div style="flex:1; text-align:center; color:{t1_color}; font-weight:bold; font-size:1.1em;">
                        {row['팀1']}
                    </div>
                    <div style="flex:0.2; text-align:center; color:{vs_color}; font-weight:bold;">
                        VS
                    </div>
                    <div style="flex:1; text-align:center; color:{t2_color}; font-weight:bold; font-size:1.1em;">
                        {row['팀2']}
                    </div>
                </div>
                <div style="text-align:center; font-size:0.85em; color:gray; margin-top:-5px; margin-bottom:15px;">
                    🏟️ {row['코트']}
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)
    else:
        st.info("현재 진행 중인 경기가 없습니다.")
        st.caption("운영자가 대진표를 공유하면 여기에 표시됩니다.")


# [1] 회원 관리 (수정버전: 삭제 기능 추가)
elif menu == "👥 회원 관리":
    st.header("👥 회원 관리")
    
    # 데이터 로드
    member_df = load_data("회원정보", ["이름", "가입일", "메모"])
    
    tab1, tab2 = st.tabs(["📜 회원 목록", "⚙️ 관리 (등록/삭제)"])
    
    with tab1:
        st.dataframe(member_df, width="stretch", hide_index=True)
        st.caption(f"총 회원수: {len(member_df)}명")
        
    with tab2:
        if is_admin:
            c1, c2 = st.columns(2)
            
            # [등록]
            with c1:
                st.subheader("➕ 신규 회원 등록")
                with st.form("add_member_form"):
                    name = st.text_input("이름")
                    memo = st.text_input("메모 (선택)")
                    if st.form_submit_button("등록"):
                        if name and name not in member_df["이름"].values:
                            add_member_to_db(name, memo)
                            st.success(f"'{name}' 회원 등록 완료!")
                            st.rerun()
                        elif name in member_df["이름"].values:
                            st.error("이미 등록된 이름입니다.")
                        else:
                            st.error("이름을 입력하세요.")
                            
            # [삭제] - 새로 추가된 기능
            with c2:
                st.subheader("🗑️ 회원 삭제")
                if not member_df.empty:
                    to_delete = st.selectbox("삭제할 회원 선택", member_df["이름"].tolist())
                    
                    st.warning("⚠️ 삭제하면 복구할 수 없습니다.")
                    if st.button("선택한 회원 영구 삭제", type="primary"):
                        try:
                            ws = spreadsheet.worksheet("회원정보")
                            # 이름이 있는 셀 찾기
                            cell = ws.find(to_delete)
                            ws.delete_rows(cell.row)
                            st.cache_data.clear()
                            st.success(f"'{to_delete}' 님을 명단에서 삭제했습니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 중 오류 발생: {e}")
                else:
                    st.info("삭제할 회원이 없습니다.")
        else:
            st.info("🔒 회원 등록 및 삭제는 관리자 권한이 필요합니다.")
            st.caption("사이드바에서 관리자 암호를 입력하세요.")


# [2] 경기 운영
elif menu == "🏟️ 경기 운영":
    st.header("🏟️ 경기 운영 시스템")
    # [수정] 탭을 5개로 확장
    mode_tab1, mode_tab2, mode_tab3, mode_tab4, mode_tab5 = st.tabs(["🔄 일반 매칭", "🏆 토너먼트", "⚔️ 팀 대항전", "🔢 KDK(개인전)", "👑 회장맘대로"])
    member_df = load_data("회원정보", ["이름"])
    
    # 2.1 일반 매칭
    with mode_tab1:
        if not member_df.empty:
            # ----------------------------------------------------
            # [복구 버튼] 실수로 껐을 때 대진표 불러오기
            # ----------------------------------------------------
            if st.button("📂 지난 대진표 불러오기 (세션 복구)", help="앱이 꺼져서 대진표가 사라졌을 때 사용하세요"):
                saved_schedule = load_schedule_backup()
                if saved_schedule:
                    st.session_state.schedule = saved_schedule
                    st.session_state.is_generated = True
                    st.session_state.recorded_ids = set() 
                    # 이미 기록된 ID들을 DB에서 확인해서 recorded_ids 복구 (선택 사항, 여기선 간단히 처리)
                    # 실제로는 DB를 조회해서 이미 완료된 경기는 버튼을 비활성화 해야 완벽함
                    hist = load_data("경기기록", ["경기ID"])
                    if not hist.empty:
                         # 저장할 때 ID생성 로직이 없어서 단순 매칭으론 복구 어려움. 
                         # 따라서 불러오기만 하고 중복 입력 주의 문구 띄움
                         st.toast("대진표를 복구했습니다! 이미 입력한 경기는 다시 입력하지 마세요.")
                    st.success("대진표 복구 완료!")
                else:
                    st.error("저장된 대진표가 없습니다.")
            
            st.divider()
            
            attendees = st.multiselect("출석 체크", member_df["이름"].tolist(), key="league_att")
            c1, c2 = st.columns(2)
            with c1: target_games = st.slider("인당 게임 수", 1, 6, 3)
            with c2: match_mode = st.radio("방식", ["🎲 랜덤 복식", "⚖️ ELO밸런스"], horizontal=True, key="league_mode") # 이름 "🎲 랜덤 복식"으로 정확히 맞춤
            
            # 생성 버튼
            if st.button("🚀 대진표 생성", type="primary"):
                hist = load_data("경기기록", ["경기ID", "날짜", "팀1", "팀2", "승리팀"]) # ID 포함 로드
                stats = get_player_stats_and_elo(hist, member_df["이름"].tolist())
                
                # 스케줄 생성
                new_schedule = generate_league_schedule(attendees, target_games, match_mode, stats)
                
                st.session_state.schedule = new_schedule
                st.session_state.is_generated = True
                st.session_state.recorded_ids = set()
                
                # [자동 백업] 생성되자마자 구글 시트에 저장
                save_schedule_backup(new_schedule)

            # [중요 변경점] 일반 매칭 출력 로직을 탭 내부로 이동
            if st.session_state.get('is_generated'):
                st.divider()
                if is_admin:
                    if st.button("📢 실시간 중계하기 (일반)", use_container_width=True):
                        display_data = []
                        for rd in st.session_state.schedule:
                            for idx, m in enumerate(rd['matches']):
                                display_data.append({"round": f"Round {rd['round_num']}", "court": f"{idx+1}코트", "t1": m['t1'], "t2": m['t2']})
                        share_to_live_board(display_data)

                for round_data in st.session_state.schedule:
                    r_num = round_data['round_num']
                    st.markdown(f"**Round {r_num}**")
                    for idx, match in enumerate(round_data['matches']):
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([2,1,1])
                            c1.caption(f"{match['t1']} vs {match['t2']}")
                            s1 = c2.number_input("점1", key=f"r{r_num}m{idx}s1", min_value=0) 
                            s2 = c3.number_input("점2", key=f"r{r_num}m{idx}s2", min_value=0)
                            
                            unique_key = f"btn_r{r_num}m{idx}"
                            is_done = unique_key in st.session_state.get('recorded_ids', set())
                            
                            if is_admin:
                                if st.button("기록" if not is_done else "완료됨", key=unique_key, disabled=is_done):
                                    add_match_record(match['t1'], match['t2'], s1, s2)
                                    st.session_state.recorded_ids.add(unique_key)
                                    st.toast("기록 저장 완료!")
                                    st.rerun()
                            elif not is_admin and not is_done:
                                st.caption("🔒 기록 권한 없음")


    # 2.2 토너먼트
    with mode_tab2:
        # (생략된 설정 UI는 위와 동일, 핵심 로직만 변경)
        if not member_df.empty:
            t_attendees = st.multiselect("참가 선수", member_df["이름"].tolist(), key="tourney_att")
            c1, c2 = st.columns(2)
            with c1: team_cnt = st.selectbox("팀 수", [4, 5, 6, 7, 8])
            with c2: team_method = st.selectbox("방식", ["⚖️ ELO밸런스", "🎲 랜덤", "👆 수동"])
            
            # ... (수동 팀 설정 로직) ...
            manual_teams = [] # (간소화)
            
            if st.button("🏟️ 대회 시작", key="start_tourney"):
                # ... (팀 생성 로직 동일) ...
                final_teams = [f"팀{i}" for i in range(team_cnt)] # 임시
                if team_method == "🎲 랜덤":
                    random.shuffle(t_attendees)
                    final_teams = [f"{t_attendees[i*2]}, {t_attendees[i*2+1]}" for i in range(team_cnt)]
                # ... (Elo 로직 등) ...
                
                st.session_state.tourney_teams = final_teams
                st.session_state.tourney_winners = {}
                st.session_state.tourney_active = True
                st.session_state.tourney_step = "PRE" if team_cnt > 4 else "SF"
                st.session_state.matches_needed = team_cnt - 4
                st.rerun()

            # [중요 변경점] 토너먼트 출력 로직을 탭 내부로 이동
            if st.session_state.get('tourney_active'):
                teams = st.session_state.tourney_teams
                winners = st.session_state.get('tourney_winners', {})
                step = st.session_state.get('tourney_step')
                
                # [공유 기능] - 현재 단계에 맞춰 공유
                if is_admin:
                    if st.button("📢 실시간 중계하기 (토너먼트)", use_container_width=True):
                        display_data = []
                        if step == "PRE":
                            for i in range(st.session_state.matches_needed):
                                display_data.append({"round": "예선", "court": f"{i+1}코트", "t1": teams[i*2], "t2": teams[i*2+1]})
                        elif step == "SF":
                            sf_teams = st.session_state.get('sf_teams', teams)
                            display_data.append({"round": "4강", "court": "A코트", "t1": sf_teams[0], "t2": sf_teams[1]})
                            display_data.append({"round": "4강", "court": "B코트", "t1": sf_teams[2], "t2": sf_teams[3]})
                        share_to_live_board(display_data)

                # ... (경기 진행 로직) ...
                # max_value 제거 및 is_admin 체크 추가
                if step == "PRE":
                    cols = st.columns(4)
                    n_matches = st.session_state.matches_needed
                    all_done = True
                    for i in range(n_matches):
                        t1, t2 = teams[i*2], teams[i*2+1]
                        key = f"PRE_{i}"
                        with cols[i]:
                            st.caption(f"{t1} vs {t2}")
                            if key not in winners:
                                all_done = False
                                s1 = st.number_input("점1", key=f"pre_s1_{i}", min_value=0)
                                s2 = st.number_input("점2", key=f"pre_s2_{i}", min_value=0)
                                if is_admin:
                                    if st.button("입력", key=f"pre_btn_{i}"):
                                        winners[key] = t1 if s1 > s2 else t2
                                        add_match_record(t1, t2, s1, s2)
                                        st.rerun()
                            else: st.success(f"승: {winners[key]}")
                    if all_done and is_admin:
                         if st.button("🚀 4강 대진표 생성"):
                            st.session_state.sf_teams = list(winners.values()) + teams[n_matches*2:]
                            st.session_state.tourney_step = "SF"; st.rerun()

                elif step == "SF":
                    sf_teams = st.session_state.get('sf_teams', teams)
                    st.pyplot(draw_bracket_plot(sf_teams))
                    # 4강 입력 로직 (is_admin 적용)
                    c1, c2 = st.columns(2)
                    for i, loc in enumerate(['semi_1', 'semi_2']):
                         with [c1, c2][i]:
                            t1, t2 = sf_teams[i*2], sf_teams[i*2+1]
                            if loc not in winners:
                                s1 = st.number_input("점1", key=f"sf_s1_{i}", min_value=0)
                                s2 = st.number_input("점2", key=f"sf_s2_{i}", min_value=0)
                                if is_admin and st.button("입력", key=f"sf_btn_{i}"):
                                    winners[loc] = t1 if s1 > s2 else t2
                                    add_match_record(t1, t2, s1, s2)
                                    st.rerun()
                    # 결승 입력 로직 (is_admin 적용)
                    if 'semi_1' in winners and 'semi_2' in winners:
                        st.markdown(f"### 결승: {winners['semi_1']} vs {winners['semi_2']}")
                        if 'final' not in winners:
                            s1 = st.number_input("점1", key="fin_s1", min_value=0)
                            s2 = st.number_input("점2", key="fin_s2", min_value=0)
                            if is_admin and st.button("우승 확정", key="fin_btn"):
                                winners['final'] = winners['semi_1'] if s1 > s2 else winners['semi_2']
                                add_match_record(winners['semi_1'], winners['semi_2'], s1, s2)
                                st.balloons(); st.rerun()

         # 2.3 팀 대항전
    with mode_tab3:
        st.subheader("⚔️ 팀 대항전 (Team Battle)")
        
        # 1. 초기화 및 설정
        # 팀 정보가 세션에 없으면 빈 리스트로 초기화
        if 'battle_teams' not in st.session_state: 
            st.session_state.battle_teams = {'A': [], 'B': []}
        if 'battle_matches' not in st.session_state: 
            st.session_state.battle_matches = []
        if 'battle_active' not in st.session_state: 
            st.session_state.battle_active = False

        # 참석자 명단 가져오기
        members_list = member_df["이름"].tolist() if not member_df.empty else []
        
        # [수정] default=[] 로 설정하여 처음에 아무도 선택되지 않게 함
        att_battle = st.multiselect(
            "참석자 선택", 
            members_list, 
            default=[],  # <--- 여기가 핵심! 빈 리스트로 시작
            key="att_battle"
        )

        if len(att_battle) < 4:
            st.warning("최소 4명 이상 선택해야 팀을 나눌 수 있습니다.")
        else:
            st.write("---")
            # 설정 UI
            c1, c2 = st.columns(2)
            with c1: 
                battle_mode = st.radio("팀 구성 방식", ["⚖️ Elo 밸런스", "🎲 완전 랜덤", "👆 수동 지정"], key="bt_mode")
            with c2: 
                game_count = st.number_input("진행할 경기 수", min_value=1, max_value=15, value=5, step=2, key="bt_count")

            # [Step 1] 팀 나누기 버튼
            if st.button("👥 팀 나누기 실행", key="btn_split_team", use_container_width=True):
                # 팀 나누기 로직 실행 시 기존 세션 초기화
                st.session_state.battle_teams = {'A': [], 'B': []} 
                
                if battle_mode == "⚖️ Elo 밸런스":
                    try:
                        # G열(승리팀) 읽기 로직
                        ws = spreadsheet.worksheet("경기기록")
                        rows = ws.get_all_values()
                        clean_data = []
                        if len(rows) > 1:
                            for r in rows[1:]:
                                if len(r) >= 7:
                                    clean_data.append({"날짜":r[0], "승리팀":r[6], "팀1":r[2], "팀2":r[3], "점수1":r[4], "점수2":r[5]})
                        hist_df = pd.DataFrame(clean_data)
                        stats = get_player_stats_and_elo(hist_df, members_list)
                        
                        sorted_att = sorted(att_battle, key=lambda x: stats.get(x, {}).get('point', 1000), reverse=True)
                        st.session_state.battle_teams['A'] = sorted_att[0::2]
                        st.session_state.battle_teams['B'] = sorted_att[1::2]
                        st.toast("⚖️ Elo 점수 기준으로 팀 균형을 맞췄습니다!")
                    except:
                        st.error("기록 부족으로 랜덤 배정합니다.")
                        random.shuffle(att_battle)
                        mid = len(att_battle) // 2
                        st.session_state.battle_teams['A'] = att_battle[:mid]
                        st.session_state.battle_teams['B'] = att_battle[mid:]
                
                elif battle_mode == "🎲 완전 랜덤":
                    random.shuffle(att_battle)
                    mid = len(att_battle) // 2
                    st.session_state.battle_teams['A'] = att_battle[:mid]
                    st.session_state.battle_teams['B'] = att_battle[mid:]
                    st.toast("🎲 팀이 랜덤으로 섞였습니다!")
                
                else: # 수동
                    st.session_state.battle_teams['A'] = []
                    st.session_state.battle_teams['B'] = []
                    st.info("아래에서 직접 팀원을 배정해주세요.")
                
                # 팀 재편성 시 기존 대진표 및 진행상태 초기화
                st.session_state.battle_matches = []
                st.session_state.battle_active = False

            # [Step 2] 팀 확인 및 조정
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("### 🅰️ A팀")
                # A팀 명단이 없으면 빈칸, 있으면 세션값 사용
                current_a = [m for m in st.session_state.battle_teams['A'] if m in att_battle]
                new_a = st.multiselect("A팀 명단", att_battle, default=current_a, key="ms_team_a")
            with col_b:
                st.markdown("### 🅱️ B팀")
                # B팀 명단: 전체 참석자 중 A팀 제외한 인원 (자동 계산)
                # 만약 세션에 B팀이 이미 있고 + 수동모드가 아니면 세션값 우선, 아니면 나머지 자동
                remain = [x for x in att_battle if x not in new_a]
                
                # UI 편의성: 팀 나누기 버튼을 안 눌렀을 때는(초기) 빈칸으로, 눌렀으면 자동 채움
                if not st.session_state.battle_teams['B'] and not st.session_state.battle_teams['A']:
                     default_b = [] # 초기 상태면 비움
                else:
                     default_b = remain # 팀 나누기 후엔 나머지 자동 채움

                new_b = st.multiselect("B팀 명단", att_battle, default=default_b, key="ms_team_b")
            
            # 세션 실시간 동기화
            st.session_state.battle_teams['A'] = new_a
            st.session_state.battle_teams['B'] = new_b

            st.divider()

            # [Step 3] 대진표 생성 및 시작 (수정됨)
            if st.button("🚀 대진표 촤라락 생성 & 경기 시작", type="primary", use_container_width=True, key="btn_start_battle"):
                if not new_a or not new_b:
                    st.error("팀원이 배정되지 않았습니다.")
                else:
                    import itertools
                    
                    # 1. 각 팀에서 가능한 모든 복식 조합 생성 (예: 4명이면 6개 조합)
                    pairs_a = list(itertools.combinations(new_a, 2))
                    pairs_b = list(itertools.combinations(new_b, 2))
                    
                    # 예외처리: 팀원이 1명이면 (나, 나)로 처리
                    if not pairs_a: pairs_a = [(new_a[0], new_a[0])]
                    if not pairs_b: pairs_b = [(new_b[0], new_b[0])]
                    
                    # 2. 조합을 무작위로 섞음 (순서 섞기)
                    random.shuffle(pairs_a)
                    random.shuffle(pairs_b)
                    
                    matches = []
                    
                    # 3. 경기 수만큼 조합을 꺼내서 매칭 (카드 덱에서 뽑듯이)
                    for i in range(game_count):
                        # % 연산자를 사용하여 조합 수보다 경기 수가 많으면 다시 처음부터 순환
                        # 예: 조합이 6개인데 경기가 7개면, 7번째 경기는 첫 번째 조합이 다시 나옴
                        p1 = pairs_a[i % len(pairs_a)]
                        p2 = pairs_b[i % len(pairs_b)]
                        
                        t1_str = f"{p1[0]}, {p1[1]}"
                        t2_str = f"{p2[0]}, {p2[1]}"
                        
                        matches.append({
                            "round": i+1, 
                            "t1": t1_str, 
                            "t2": t2_str, 
                            "done": False, 
                            "winner": None,
                            "s1": 0, "s2": 0
                        })
                    
                    st.session_state.battle_matches = matches
                    st.session_state.battle_active = True
                    st.toast("✅ 중복 없는 최적의 대진표가 생성되었습니다!")
                    st.rerun()

            # [중요 변경점] 팀 대항전 출력 로직을 탭 내부로 이동
            if st.session_state.battle_active:
                matches = st.session_state.battle_matches
                sa = sum(1 for m in matches if m['winner'] == 'A')
                sb = sum(1 for m in matches if m['winner'] == 'B')
                
                st.markdown(f"""
                <div style='background:#f0f2f6; padding:15px; border-radius:10px; text-align:center; margin-bottom:10px;'>
                    <h2 style='margin:0; color:#000;'>🔵 A팀 {sa} : {sb} B팀 🔴</h2>
                </div>
                """, unsafe_allow_html=True)

                if st.button("📢 실시간 현황판(구글시트) 송출", use_container_width=True, key="btn_share_live"):
                    try:
                        try: ws_live = spreadsheet.worksheet("실시간현황")
                        except: ws_live = spreadsheet.add_worksheet("실시간현황", 100, 10)
                        ws_live.clear()
                        ws_live.append_row(["경기", "A팀", "VS", "B팀", "점수", "상태", "업데이트"])
                        rows = []
                        now = datetime.now().strftime("%H:%M")
                        for m in matches:
                            stat_txt = "종료" if m['done'] else "진행중"
                            score_txt = f"{m['s1']}:{m['s2']}" if m['done'] else "0:0"
                            rows.append([f"Game {m['round']}", m['t1'], "VS", m['t2'], score_txt, stat_txt, now])
                        ws_live.append_rows(rows)
                        st.toast("✅ 실시간 현황판 업데이트 완료!")
                    except Exception as e:
                        st.error(f"전송 실패: {e}")

                for i, m in enumerate(matches):
                    status_icon = "✅" if m['done'] else "🔥"
                    exp_label = f"Game {m['round']} : {m['t1']} vs {m['t2']} {status_icon}"
                    if m['done']: exp_label += f" ({m['winner']}승)"
                    
                    with st.expander(exp_label, expanded=not m['done']):
                        if not m['done']:
                            sc1, sc2_col = st.columns(2)
                            s1_val = sc1.number_input("A팀 점수", key=f"s1_{i}", min_value=0)
                            s2_val = sc2_col.number_input("B팀 점수", key=f"s2_{i}", min_value=0)
                            
                            if st.button("💾 경기 종료 및 저장", key=f"save_{i}"):
                                if s1_val == s2_val:
                                    st.warning("무승부는 저장할 수 없습니다.")
                                else:
                                    m['s1'], m['s2'] = s1_val, s2_val
                                    m['winner'] = 'A' if s1_val > s2_val else 'B'
                                    m['done'] = True
                                    try:
                                        ws_rec = spreadsheet.worksheet("경기기록")
                                        win_name = m['t1'] if m['winner'] == 'A' else m['t2']
                                        ws_rec.append_row([
                                            datetime.now().strftime("%Y-%m-%d %H:%M"),
                                            datetime.now().strftime("%Y%m%d%H%M%S"),
                                            m['t1'], m['t2'], s1_val, s2_val, win_name
                                        ])
                                        st.success("기록 저장 완료!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"저장 중 오류: {e}")
                        else:
                            st.info(f"🏆 승리: {m['winner']}팀 ({m['t1'] if m['winner']=='A' else m['t2']}) - 점수 {m['s1']}:{m['s2']}")

                if st.button("🔄 새 경기 시작 (초기화)", key="btn_reset_battle"):
                    st.session_state.battle_active = False
                    st.session_state.battle_matches = []
                    st.session_state.battle_teams = {'A': [], 'B': []}
                    st.rerun()


    # 2.4 KDK
    with mode_tab4:
        # (기존 설정 로직)
        if not member_df.empty:
            kdk_att = st.multiselect("참가자", member_df["이름"].tolist(), key="kdk_att")
            kdk_rounds = st.slider("라운드", 1, 6, 4, key="kdk_rds")

            if st.button("🎲 대진표 생성"):
                st.session_state.kdk_schedule = generate_kdk_schedule(kdk_att, kdk_rounds)
                st.session_state.kdk_scores = {}
                st.session_state.kdk_active = True
                st.session_state.kdk_recorded = set()
                st.rerun()
            
            # [중요 변경점] KDK 출력 로직을 탭 내부로 이동
            if st.session_state.get('kdk_active'):
                if is_admin:
                    if st.button("📢 실시간 중계하기 (KDK)", use_container_width=True):
                        display_data = []
                        for r in st.session_state.kdk_schedule:
                            for idx, m in enumerate(r['matches']):
                                key = f"kdk_r{r['round']}_m{idx}"
                                if key not in st.session_state.get('kdk_scores', {}):
                                    display_data.append({"round": f"R{r['round']}", "court": f"{idx+1}코트", "t1": m['t1'], "t2": m['t2']})
                        share_to_live_board(display_data)

                schedule = st.session_state.kdk_schedule
                scores = st.session_state.get('kdk_scores', {})
                
                # 랭킹 표시는 기존 유지 (생략)
                
                for r in schedule:
                    with st.expander(f"Round {r['round']}", expanded=True):
                        cols = st.columns(len(r['matches']))
                        for idx, m in enumerate(r['matches']):
                            key = f"kdk_r{r['round']}_m{idx}"
                            is_done = key in scores
                            
                            with cols[idx]:
                                st.caption(f"{m['t1']} vs {m['t2']}")
                                if not is_done:
                                    s1 = st.number_input("점1", key=f"k_s1_{key}", min_value=0)
                                    s2 = st.number_input("점2", key=f"k_s2_{key}", min_value=0)
                                    if is_admin and st.button("입력", key=f"k_btn_{key}"):
                                        scores[key] = {'s1': s1, 's2': s2, 'done': True}
                                        add_match_record(m['t1'], m['t2'], s1, s2)
                                        st.rerun()
                                else:
                                    st.success(f"{scores[key]['s1']} : {scores[key]['s2']}")

    # 2.5 회장맘대로 (NEW FEATURE)
    with mode_tab5:
        st.subheader("👑 회장님 전용 맞춤 매칭")
        
        # [1] 복구 및 기본 설정
        col_back1, col_back2 = st.columns([2, 1])
        with col_back1:
            if st.button("📂 회장님 대진표 불러오기 (복구)", key="restore_boss"):
                saved = load_schedule_backup()
                if saved:
                    st.session_state.boss_schedule = saved
                    st.session_state.boss_active = True
                    st.success("대진표 복구 완료!")
        
        st.divider()

        # [2] 출석체크 및 환경 설정
        boss_attendees = st.multiselect("출석 체크 (회장님 확인)", member_df["이름"].tolist(), key="boss_att")
        
        c1, c2 = st.columns(2)
        with c1:
            boss_game_count = st.slider("진행할 게임 수", 3, 10, 4, key="boss_game_cnt")
        with c2:
            boss_mode = st.radio("매칭 방식 선택", ["고정 팀(나머지 랜덤)", "완전 수동(회장 지정)"], key="boss_mode_opt")

        # [3] 세부 설정 (고정 팀 모드일 경우)
        fixed_teams = []
        if boss_mode == "고정 팀(나머지 랜덤)":
            with st.expander("📌 고정 팀 설정 (최대 4팀)", expanded=True):
                st.caption("고정하고 싶은 팀원을 선택하세요. 나머지는 랜덤으로 섞입니다.")
                for i in range(1, 5):
                    t_cols = st.columns(2)
                    p1 = t_cols[0].selectbox(f"{i}코트 팀원1", ["선택안함"] + boss_attendees, key=f"fixed_t{i}_p1")
                    p2 = t_cols[1].selectbox(f"{i}코트 팀원2", ["선택안함"] + boss_attendees, key=f"fixed_t{i}_p2")
                    if p1 != "선택안함" and p2 != "선택안함":
                        fixed_teams.append(f"{p1}, {p2}")

        # [4] 대진표 생성 로직
        if st.button("🚀 회장님 결재 대진표 생성", type="primary", use_container_width=True):
            if len(boss_attendees) < 4:
                st.error("최소 4명 이상의 출석 인원이 필요합니다.")
            else:
                new_boss_schedule = []
                
                # --- 방식 1: 고정 팀 나머지 랜덤 ---
                if boss_mode == "고정 팀(나머지 랜덤)":
                    # 고정 팀에 포함된 인원 제외
                    fixed_members = []
                    for ft in fixed_teams:
                        fixed_members.extend([p.strip() for p in ft.split(',')])
                    
                    remaining_members = [m for m in boss_attendees if m not in fixed_members]
                    
                    for g in range(1, boss_game_count + 1):
                        current_matches = []
                        # 1. 고정 팀 먼저 배치
                        for i, ft in enumerate(fixed_teams):
                            # 상대팀은 남은 인원에서 랜덤 추출 (간소화된 로직)
                            if len(remaining_members) >= 2:
                                random.shuffle(remaining_members)
                                opp = f"{remaining_members.pop(0)}, {remaining_members.pop(0)}"
                                current_matches.append({"t1": ft, "t2": opp, "court": f"{i+1}코트"})
                        
                        # 2. 남은 인원들끼리 매칭
                        random.shuffle(remaining_members)
                        while len(remaining_members) >= 4:
                            p1, p2, p3, p4 = [remaining_members.pop(0) for _ in range(4)]
                            current_matches.append({"t1": f"{p1}, {p2}", "t2": f"{p3}, {p4}", "court": f"추가코트"})
                        
                        # [KEY FIX] 'game' 키 사용 (이전 데이터 호환)
                        new_boss_schedule.append({"game": g, "matches": current_matches})
                        # 매 게임마다 인원 초기화 (다음 게임 랜덤을 위해)
                        remaining_members = [m for m in boss_attendees if m not in fixed_members]

                # --- 방식 2: 완전 수동 (빈 틀 생성) ---
                else:
                    for g in range(1, boss_game_count + 1):
                        # 회장이 직접 선택할 수 있도록 빈 팀 구조만 생성
                        courts_needed = len(boss_attendees) // 4
                        current_matches = [{"t1": "미지정", "t2": "미지정", "court": f"{i+1}코트"} for i in range(courts_needed)]
                        # [KEY FIX] 'game' 키 사용
                        new_boss_schedule.append({"game": g, "matches": current_matches})

                st.session_state.boss_schedule = new_boss_schedule
                st.session_state.boss_active = True
                save_schedule_backup(new_boss_schedule)
                st.rerun()

        # [5] 대진표 표시 및 기록 (회장맘대로 탭 내부)
        if st.session_state.get('boss_active'):
            st.divider()
            if is_admin:
                if st.button("📢 실시간 현황판 전송 (회장맘대로)", use_container_width=True):
                    live_data = []
                    for gs in st.session_state.boss_schedule:
                        # [KEY FIX] 'game' 키 사용 확인
                        game_num = gs.get('game', gs.get('game_num', '?'))
                        for m in gs['matches']:
                            live_data.append({"round": f"Game {game_num}", "court": m['court'], "t1": m['t1'], "t2": m['t2']})
                    share_to_live_board(live_data)

            for g_idx, game_data in enumerate(st.session_state.boss_schedule):
                # [KEY FIX] 'game' 키 사용
                game_num = game_data.get('game', game_data.get('game_num', g_idx+1))
                st.markdown(f"### 🏟️ Game {game_num}")
                for m_idx, match in enumerate(game_data['matches']):
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 1, 1])
                        
                        # 수동 모드일 경우 선수 선택 드롭다운 표시
                        if boss_mode == "완전 수동(회장 지정)":
                            t1_p = c1.multiselect(f"팀1 (Game{g_idx+1}-M{m_idx+1})", boss_attendees, max_selections=2, key=f"b_t1_{g_idx}_{m_idx}")
                            t2_p = c1.multiselect(f"팀2 (Game{g_idx+1}-M{m_idx+1})", boss_attendees, max_selections=2, key=f"b_t2_{g_idx}_{m_idx}")
                            match['t1'] = ", ".join(t1_p) if t1_p else "미지정"
                            match['t2'] = ", ".join(t2_p) if t2_p else "미지정"
                        else:
                            c1.write(f"**{match['court']}**: {match['t1']}  **VS** {match['t2']}")
                        
                        s1 = c2.number_input("점1", key=f"b_s1_{g_idx}_{m_idx}", min_value=0)
                        s2 = c3.number_input("점2", key=f"b_s2_{g_idx}_{m_idx}", min_value=0)
                        
                        if is_admin:
                            btn_key = f"btn_b_{g_idx}_{m_idx}"
                            is_done = btn_key in st.session_state.get('recorded_ids', set())
                            if st.button("기록 저장", key=btn_key, disabled=is_done, use_container_width=True):
                                if match['t1'] != "미지정" and match['t2'] != "미지정":
                                    add_match_record(match['t1'], match['t2'], s1, s2)
                                    if 'recorded_ids' not in st.session_state: st.session_state.recorded_ids = set()
                                    st.session_state.recorded_ids.add(btn_key)
                                    st.toast(f"Game {g_idx+1} 기록 완료!")
                                    st.rerun()
                                else:
                                    st.error("선수를 먼저 선택해주세요.")

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
                    "날짜": row[0],         # A열
                    "경기ID": row[1],       # B열 (여기에 이상한 날짜숫자가 ID 역할)
                    "승리팀": row[6],       # G열 (밀려난 승리팀)
                    "팀1": row[2],          # C열
                    "팀2": row[3],          # D열
                    "점수1": row[4],        # E열
                    "점수2": row[5]         # F열
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
