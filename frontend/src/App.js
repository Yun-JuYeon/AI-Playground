import React, { useState, useEffect, useRef } from 'react';
import './App.css';

function App() {
  const [username, setUsername] = useState('');
  const [isJoined, setIsJoined] = useState(false);
  const [gameMode, setGameMode] = useState(null);
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [ws, setWs] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // 끝말잇기 상태
  const [wordList, setWordList] = useState([]);
  const [currentWord, setCurrentWord] = useState('');
  const [score, setScore] = useState(0);
  const [isGameOver, setIsGameOver] = useState(false);
  const [gameOverMessage, setGameOverMessage] = useState('');
  const [wordChainWs, setWordChainWs] = useState(null);
  const [difficulty, setDifficulty] = useState(3);
  const [showDifficultySelect, setShowDifficultySelect] = useState(false);
  const [gameHistory, setGameHistory] = useState([]);
  const [selectedGame, setSelectedGame] = useState(null);
  const wordListRef = useRef(null);
  const [wcErrorMessage, setWcErrorMessage] = useState('');

  // 채팅 히스토리 상태
  const [chatSessions, setChatSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const scrollWordListToEnd = () => {
    if (wordListRef.current) {
      wordListRef.current.scrollLeft = wordListRef.current.scrollWidth;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    scrollWordListToEnd();
  }, [wordList]);

  const fetchGameHistory = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/wordchain/history/' + username);
      if (response.ok) {
        const data = await response.json();
        setGameHistory(data.history || []);
      }
    } catch (error) {
      console.error('Failed to fetch history:', error);
    }
  };

  const fetchChatSessions = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/chat/sessions/' + username);
      if (response.ok) {
        const data = await response.json();
        setChatSessions(data.sessions || []);
        setCurrentSessionId(data.current_id || null);
      }
    } catch (error) {
      console.error('Failed to fetch chat sessions:', error);
    }
  };

  const handleLogin = () => {
    if (!username.trim()) return;
    setIsJoined(true);
  };

  const selectMode = async (mode) => {
    if (mode === 'chat') {
      setGameMode(mode);
      await fetchChatSessions();
      connectChat();
    } else if (mode === 'wordchain') {
      setShowDifficultySelect(true);
    }
  };

  const startWordChain = async (selectedDifficulty) => {
    setDifficulty(selectedDifficulty);
    setShowDifficultySelect(false);
    setGameMode('wordchain');
    await fetch('http://localhost:8000/api/wordchain/restart/' + username, { method: 'POST' });
    await fetchGameHistory();
    connectWordChain(selectedDifficulty);
  };

  const goBack = () => {
    if (ws) ws.close();
    if (wordChainWs) wordChainWs.close();
    setWs(null);
    setWordChainWs(null);
    setGameMode(null);
    setMessages([]);
    setWordList([]);
    setCurrentWord('');
    setScore(0);
    setIsGameOver(false);
    setGameOverMessage('');
    setShowDifficultySelect(false);
    setGameHistory([]);
    setSelectedGame(null);
    setChatSessions([]);
    setCurrentSessionId(null);
  };

  const logout = () => {
    goBack();
    setUsername('');
    setIsJoined(false);
  };

  const connectChat = () => {
    const websocket = new WebSocket('ws://localhost:8000/ws/' + username);
    websocket.onopen = () => console.log('Chat connected');
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'session_info') {
        setCurrentSessionId(data.session_id);
      } else if (data.type === 'history') {
        setMessages(data.messages);
      } else if (data.type === 'session_updated') {
        fetchChatSessions();
      } else if (data.type === 'message' || data.type === 'system') {
        setMessages((prev) => [...prev, data]);
      }
    };
    websocket.onclose = () => console.log('Chat disconnected');
    setWs(websocket);
  };

  const connectWordChain = (diff) => {
    const websocket = new WebSocket('ws://localhost:8000/ws/wordchain/' + username + '/' + diff);
    websocket.onopen = () => console.log('WordChain connected');
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'history') {
        // 무시 - 새 게임
      } else if (data.type === 'game_over') {
        setIsGameOver(true);
        setGameOverMessage(data.message);
        fetchGameHistory();
      } else if (data.type === 'score') {
        setScore(data.score);
      } else if (data.type === 'system') {
        // 에러 메시지 표시
        setWcErrorMessage(data.message);
        setTimeout(() => setWcErrorMessage(''), 3000);
      } else if (data.type === 'message') {
        setWcErrorMessage(''); // 성공하면 에러 메시지 클리어
        const newWord = { word: data.message, isUser: data.username !== 'AI' };
        setWordList((prev) => [...prev, newWord]);
        setCurrentWord(data.message);
      }
    };
    websocket.onclose = () => console.log('WordChain disconnected');
    setWordChainWs(websocket);
  };

  const sendMessage = (e) => {
    e.preventDefault();
    if (!message.trim() || !ws) return;
    ws.send(message);
    setMessage('');
  };

  const sendWord = (e) => {
    e.preventDefault();
    if (!message.trim() || !wordChainWs || isGameOver) return;
    wordChainWs.send(message);
    setMessage('');
  };

  const startNewChat = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/chat/new/' + username, { method: 'POST' });
      if (response.ok) {
        setMessages([]);
        if (ws) ws.close();
        await fetchChatSessions();
        setTimeout(() => connectChat(), 100);
      }
    } catch (error) {
      console.error('Failed to create new chat:', error);
    }
    setIsLoading(false);
  };

  const switchChatSession = async (sessionId) => {
    if (sessionId === currentSessionId) return;
    setIsLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/chat/switch/${username}/${sessionId}`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setMessages(data.messages || []);
          setCurrentSessionId(sessionId);
          if (ws) ws.close();
          setTimeout(() => connectChat(), 100);
        }
      }
    } catch (error) {
      console.error('Failed to switch session:', error);
    }
    setIsLoading(false);
  };

  const deleteChatSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm('이 대화를 삭제할까요?')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/chat/session/${username}/${sessionId}`, { method: 'DELETE' });
      if (response.ok) {
        await fetchChatSessions();
        // 현재 세션이 삭제되었으면 다른 세션으로 전환하거나 새로 시작
        if (sessionId === currentSessionId) {
          setMessages([]);
          if (ws) ws.close();
          setTimeout(() => connectChat(), 100);
        }
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const restartWordChain = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/wordchain/restart/' + username, { method: 'POST' });
      if (response.ok) {
        setWordList([]);
        setCurrentWord('');
        setScore(0);
        setIsGameOver(false);
        setGameOverMessage('');
        if (wordChainWs) wordChainWs.close();
        setTimeout(() => connectWordChain(difficulty), 100);
      }
    } catch (error) {
      console.error('Failed to restart game:', error);
      alert('게임 재시작에 실패했습니다.');
    }
  };

  const deleteGameHistory = async (e, index) => {
    e.stopPropagation();
    if (!window.confirm('이 게임 기록을 삭제할까요?')) return;

    try {
      const response = await fetch(`http://localhost:8000/api/wordchain/history/${username}/${index}`, { method: 'DELETE' });
      if (response.ok) {
        await fetchGameHistory();
        if (selectedGame === index) {
          setSelectedGame(null);
        } else if (selectedGame !== null && selectedGame > index) {
          setSelectedGame(selectedGame - 1);
        }
      }
    } catch (error) {
      console.error('Failed to delete game history:', error);
    }
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getLastChar = (word) => {
    if (!word) return '';
    return word[word.length - 1];
  };

  const difficultyInfo = {
    1: { name: '아주 쉬움', emoji: '😊', color: '#a8e6cf', desc: 'AI가 쉬운 단어만 사용' },
    2: { name: '쉬움', emoji: '🙂', color: '#88d8b0', desc: 'AI가 가끔 포기함' },
    3: { name: '보통', emoji: '😐', color: '#ffd3a5', desc: '공정한 대결' },
    4: { name: '어려움', emoji: '😤', color: '#ffb347', desc: 'AI가 어려운 단어 사용' },
    5: { name: '전문가', emoji: '🔥', color: '#ff6b6b', desc: 'AI가 이기려고 함!' }
  };

  // 로그인 화면
  if (!isJoined) {
    return (
      <div className="join-container">
        <div className="join-box">
          <h1>AI 플레이그라운드</h1>
          <input
            type="text"
            placeholder="닉네임을 입력하세요"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleLogin()}
          />
          <button onClick={handleLogin}>시작하기</button>
        </div>
      </div>
    );
  }

  // 난이도 선택 화면
  if (showDifficultySelect) {
    return (
      <div className="join-container">
        <div className="difficulty-select-box">
          <button className="diff-back-btn" onClick={() => setShowDifficultySelect(false)}>←</button>
          <button className="box-logout-btn" onClick={logout}>로그아웃</button>
          <h1>난이도 선택</h1>
          <p className="diff-subtitle">AI의 실력을 선택하세요!</p>
          <div className="difficulty-options">
            {[1, 2, 3, 4, 5].map((level) => (
              <button
                key={level}
                className={'diff-btn' + (difficulty === level ? ' selected' : '')}
                style={{ '--diff-color': difficultyInfo[level].color }}
                onClick={() => startWordChain(level)}
              >
                <span className="diff-emoji">{difficultyInfo[level].emoji}</span>
                <span className="diff-level">Lv.{level}</span>
                <span className="diff-name">{difficultyInfo[level].name}</span>
                <span className="diff-desc">{difficultyInfo[level].desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // 모드 선택 화면
  if (!gameMode) {
    return (
      <div className="join-container">
        <div className="mode-select-box">
          <button className="box-logout-btn" onClick={logout}>로그아웃</button>
          <h1>무엇을 할까요?</h1>
          <p className="welcome-text">{username}님, 환영합니다!</p>
          <div className="mode-buttons">
            <button className="mode-btn chat-mode" onClick={() => selectMode('chat')}>
              <span className="mode-icon">💬</span>
              <span className="mode-title">AI 채팅</span>
              <span className="mode-desc">AI와 자유롭게 대화하기</span>
            </button>
            <button className="mode-btn wordchain-mode" onClick={() => selectMode('wordchain')}>
              <span className="mode-icon">🎮</span>
              <span className="mode-title">끝말잇기</span>
              <span className="mode-desc">AI와 끝말잇기 대결!</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 채팅 화면
  if (gameMode === 'chat') {
    return (
      <div className="chat-page">
        {/* 사이드바 */}
        <div className="chat-sidebar">
          <div className="chat-sidebar-header">
            <h3>대화 기록</h3>
          </div>
          <div className="chat-sidebar-content">
            {chatSessions.length === 0 ? (
              <div className="chat-no-history">아직 기록이 없어요!</div>
            ) : (
              chatSessions.map((session) => (
                <div
                  key={session.id}
                  className={'chat-history-item' + (session.id === currentSessionId ? ' current' : '')}
                  onClick={() => switchChatSession(session.id)}
                >
                  <button
                    className="chat-history-delete"
                    onClick={(e) => deleteChatSession(e, session.id)}
                  >×</button>
                  {session.id === currentSessionId && (
                    <div className="chat-history-label">현재 대화</div>
                  )}
                  <div className="chat-history-preview">{session.preview}</div>
                  <div className="chat-history-info">
                    <span className="chat-history-count">{session.message_count}개 메시지</span>
                  </div>
                  <div className="chat-history-date">{formatDate(session.updated_at)}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 메인 채팅 영역 */}
        <div className="chat-main-area">
          <div className="chat-header">
            <div className="header-left">
              <button className="chat-back-btn" onClick={goBack}>← 나가기</button>
              <h2>AI 채팅</h2>
            </div>
            <div className="header-actions">
              <span className="chat-user-badge">{username}님</span>
              <button className="chat-new-btn" onClick={startNewChat} disabled={isLoading}>+ 새 대화</button>
              <button className="chat-logout-btn" onClick={logout}>로그아웃</button>
            </div>
          </div>
          <div className="messages-container">
            {messages.map((msg, index) => (
              <div key={index} className={'message ' + (msg.type === 'system' ? 'system' : msg.username === username ? 'mine' : 'others')}>
                {msg.type === 'system' ? (
                  <span className="system-message">{msg.message}</span>
                ) : (
                  <>
                    {msg.username !== username && <span className="username">{msg.username}</span>}
                    <div className="message-content">
                      <span className="text">{msg.message}</span>
                      <span className="time">{formatTime(msg.timestamp)}</span>
                    </div>
                  </>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          <form className="input-container" onSubmit={sendMessage}>
            <input type="text" placeholder="메시지를 입력하세요..." value={message} onChange={(e) => setMessage(e.target.value)} />
            <button type="submit">전송</button>
          </form>
        </div>
      </div>
    );
  }

  // 끝말잇기 화면
  if (gameMode === 'wordchain') {
    return (
      <div className="wc-page">
        {/* 사이드바 - 항상 고정 */}
        <div className="wc-sidebar">
          <div className="wc-sidebar-header">
            <h3>게임 기록</h3>
          </div>
          <div className="wc-sidebar-content">
            {gameHistory.length === 0 ? (
              <div className="wc-no-history">아직 기록이 없어요!</div>
            ) : (
              gameHistory.map((game, index) => (
                <div
                  key={index}
                  className="wc-history-item"
                  onClick={() => setSelectedGame(selectedGame === index ? null : index)}
                >
                  <button
                    className="wc-history-delete"
                    onClick={(e) => deleteGameHistory(e, index)}
                  >×</button>
                  <div className="wc-history-result">
                    {game.result === 'win' ? '🏆 승리' : '💔 패배'}
                  </div>
                  <div className="wc-history-info">
                    <span className="wc-history-score">{game.score}점</span>
                    <span className="wc-history-words">{game.words_count}단어</span>
                    <span className="wc-history-diff" style={{ background: difficultyInfo[game.difficulty]?.color }}>
                      Lv.{game.difficulty}
                    </span>
                  </div>
                  <div className="wc-history-date">{formatDate(game.timestamp)}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 게임 기록 상세 모달 */}
        {selectedGame !== null && gameHistory[selectedGame] && (
          <div className="wc-modal-overlay" onClick={() => setSelectedGame(null)}>
            <div className="wc-modal" onClick={(e) => e.stopPropagation()}>
              <div className="wc-modal-header">
                <h3>게임 기록 상세</h3>
                <button className="wc-modal-close" onClick={() => setSelectedGame(null)}>×</button>
              </div>
              <div className="wc-modal-body">
                <div className="wc-modal-info">
                  <span className="wc-modal-result">
                    {gameHistory[selectedGame].result === 'win' ? '🏆 승리' : '💔 패배'}
                  </span>
                  <span className="wc-modal-score">{gameHistory[selectedGame].score}점</span>
                  <span
                    className="wc-modal-diff"
                    style={{ background: difficultyInfo[gameHistory[selectedGame].difficulty]?.color }}
                  >
                    Lv.{gameHistory[selectedGame].difficulty}
                  </span>
                </div>
                <div className="wc-modal-date">{formatDate(gameHistory[selectedGame].timestamp)}</div>
                <div className="wc-modal-words-title">사용된 단어 ({gameHistory[selectedGame].words_count}개)</div>
                <div className="wc-modal-words">
                  {gameHistory[selectedGame].words?.map((word, i) => (
                    <span key={i} className="wc-modal-word">{word}</span>
                  )) || <span className="wc-modal-no-words">단어 기록 없음</span>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 메인 게임 - 완전 중앙 정렬 */}
        <div className="wc-main-area">
          {/* 상단 헤더 */}
          <div className="wc-top-bar">
            <button className="wc-back-btn" onClick={goBack}>← 나가기</button>
            <div className="wc-top-bar-right">
              <span className="wc-user-badge">{username}님</span>
              <button className="wc-logout-btn" onClick={logout}>로그아웃</button>
            </div>
          </div>

          {/* 중앙 게임 영역 */}
          <div className="wc-center-area">
            {/* 점수/난이도 - 중앙 상단 */}
            <div className="wc-game-status">
              <span className="wc-difficulty-badge" style={{ background: difficultyInfo[difficulty].color }}>
                {difficultyInfo[difficulty].emoji} Lv.{difficulty} {difficultyInfo[difficulty].name}
              </span>
              <span className="wc-score-badge">점수: {score}</span>
            </div>

            {/* 단어 리스트 - 가로+세로 확장 */}
            <div className="wc-word-list-wrapper">
              <div className="wc-word-list" ref={wordListRef}>
                {wordList.length === 0 ? (
                  <div className="wc-empty-list">단어가 여기에 표시됩니다</div>
                ) : (
                  wordList.map((item, index) => (
                    <span key={index} className={'wc-word ' + (item.isUser ? 'user' : 'ai')}>
                      {item.word}
                    </span>
                  ))
                )}
              </div>
            </div>

            {/* 현재 단어 크게 표시 */}
            <div className="wc-current-display">
              {currentWord ? (
                <>
                  <div className="wc-big-word">{currentWord}</div>
                  <div className="wc-next-hint">
                    <span className="wc-next-char">{getLastChar(currentWord)}</span>
                    <span>(으)로 시작하는 단어를 입력하세요!</span>
                  </div>
                </>
              ) : (
                <div className="wc-start-prompt">
                  <div className="wc-start-emoji">🎯</div>
                  <div>아무 단어나 입력해서 시작!</div>
                </div>
              )}
            </div>

            {/* 게임 오버 메시지 */}
            {isGameOver && (
              <div className="wc-gameover-banner">
                {gameOverMessage}
              </div>
            )}

            {/* 에러 메시지 */}
            {wcErrorMessage && (
              <div className="wc-error-message">
                ⚠️ {wcErrorMessage}
              </div>
            )}

            {/* 입력 영역 */}
            <div className="wc-input-box">
              <form className="wc-input-form" onSubmit={sendWord}>
                <input
                  type="text"
                  className="wc-text-input"
                  placeholder={isGameOver ? "게임 종료!" : "단어 입력..."}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  disabled={isGameOver}
                  autoFocus
                />
                <button type="submit" className="wc-send-btn" disabled={isGameOver}>
                  입력
                </button>
              </form>
              <button className="wc-restart-button" onClick={restartWordChain}>
                🔄 다시 시작
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

export default App;
