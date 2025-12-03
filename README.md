# AI 플레이그라운드 🎮💬

AI와 채팅하고 끝말잇기 게임을 즐길 수 있는 웹 애플리케이션입니다.

## 기능

### 💬 AI 채팅
- OpenAI GPT-4o-mini 기반 대화
- 대화 기록 저장 (Redis)
- 재접속 시 이전 대화 이어가기

### 🎮 끝말잇기
- AI와 끝말잇기 대결
- 점수 시스템
- 게임 기록 저장

## 기술 스택

### Frontend
- React 18
- CSS3 (파스텔톤 그라데이션 UI)

### Backend
- FastAPI
- WebSocket (실시간 통신)
- OpenAI API
- Redis (데이터 저장)

## 설치 및 실행

### 1. 사전 요구사항
- Python 3.10+
- Node.js 18+
- Redis

### 2. 백엔드 설정

```bash
cd backend

# 가상환경 생성 및 활성화
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 패키지 설치
pip install fastapi uvicorn websockets openai python-dotenv redis

# 환경 변수 설정
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 입력

# 서버 실행
uvicorn main:app --reload
```

### 3. 프론트엔드 설정

```bash
cd frontend

# 패키지 설치
npm install

# 개발 서버 실행
npm start
```

### 4. Redis 실행

```bash
# Docker 사용 시
docker run -d -p 6379:6379 redis

# 또는 로컬 Redis 서버 실행
redis-server
```

## 환경 변수

`backend/.env` 파일에 다음 내용을 설정하세요:

```
OPENAI_API_KEY=your_openai_api_key
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 스크린샷

| 로그인 | 모드 선택 |
|--------|-----------|
| 닉네임 입력 | 채팅 / 끝말잇기 선택 |

| AI 채팅 | 끝말잇기 |
|---------|----------|
| GPT와 대화 | AI와 끝말잇기 대결 |

## 라이선스

MIT License
