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

  const [wordChainMessages, setWordChainMessages] = useState([]);
  const [score, setScore] = useState(0);
  const [isGameOver, setIsGameOver] = useState(false);
  const [wordChainWs, setWordChainWs] = useState(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, wordChainMessages]);

  const handleLogin = () => {
    if (!username.trim()) return;
    setIsJoined(true);
  };

  const selectMode = (mode) => {
    setGameMode(mode);
    if (mode === 'chat') connectChat();
    else if (mode === 'wordchain') connectWordChain();
  };

  const goBack = () => {
    if (ws) ws.close();
    if (wordChainWs) wordChainWs.close();
    setWs(null);
    setWordChainWs(null);
    setGameMode(null);
    setMessages([]);
    setWordChainMessages([]);
    setScore(0);
    setIsGameOver(false);
  };

  const connectChat = () => {
    const websocket = new WebSocket('ws://localhost:8000/ws/' + username);
    websocket.onopen = () => console.log('Chat connected');
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'history') setMessages(data.messages);
      else setMessages((prev) => [...prev, data]);
    };
    websocket.onclose = () => console.log('Chat disconnected');
    setWs(websocket);
  };

  const connectWordChain = () => {
    const websocket = new WebSocket('ws://localhost:8000/ws/wordchain/' + username);
    websocket.onopen = () => console.log('WordChain connected');
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'history') {
        setWordChainMessages(data.messages);
        if (data.score !== undefined) setScore(data.score);
        if (data.isGameOver !== undefined) setIsGameOver(data.isGameOver);
      } else if (data.type === 'game_over') {
        setIsGameOver(true);
        setWordChainMessages((prev) => [...prev, data]);
      } else if (data.type === 'score') {
        setScore(data.score);
      } else {
        setWordChainMessages((prev) => [...prev, data]);
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

  const clearChat = async () => {
    if (!window.confirm('대화 기록을 모두 삭제하고 새로 시작할까요?')) return;
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/clear/' + username, { method: 'POST' });
      if (response.ok) {
        setMessages([]);
        if (ws) ws.close();
        setTimeout(() => connectChat(), 100);
      }
    } catch (error) {
      console.error('Failed to clear chat:', error);
      alert('대화 초기화에 실패했습니다.');
    }
    setIsLoading(false);
  };

  const restartWordChain = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/wordchain/restart/' + username, { method: 'POST' });
      if (response.ok) {
        setWordChainMessages([]);
        setScore(0);
        setIsGameOver(false);
        if (wordChainWs) wordChainWs.close();
        setTimeout(() => connectWordChain(), 100);
      }
    } catch (error) {
      console.error('Failed to restart game:', error);
      alert('게임 재시작에 실패했습니다.');
    }
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  };

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

  if (!gameMode) {
    return (
      <div className="join-container">
        <div className="mode-select-box">
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

  if (gameMode === 'chat') {
    return (
      <div className="chat-container">
        <div className="chat-header">
          <div className="header-left">
            <button className="back-btn" onClick={goBack}>←</button>
            <h2>AI 채팅</h2>
          </div>
          <div className="header-actions">
            <span className="user-status">{username}님</span>
            <button className="clear-btn" onClick={clearChat} disabled={isLoading}>새 대화</button>
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
    );
  }

  if (gameMode === 'wordchain') {
    return (
      <div className="chat-container wordchain-container">
        <div className="chat-header wordchain-header">
          <div className="header-left">
            <button className="back-btn" onClick={goBack}>←</button>
            <h2>끝말잇기</h2>
          </div>
          <div className="header-actions">
            <span className="score-display">점수: {score}</span>
            <button className="clear-btn" onClick={restartWordChain}>다시 시작</button>
          </div>
        </div>
        <div className="messages-container">
          {wordChainMessages.map((msg, index) => (
            <div key={index} className={'message ' + (msg.type === 'system' || msg.type === 'game_over' ? 'system' : msg.username === username ? 'mine' : 'others')}>
              {msg.type === 'system' || msg.type === 'game_over' ? (
                <span className={'system-message ' + (msg.type === 'game_over' ? 'game-over' : '')}>{msg.message}</span>
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
        <form className="input-container" onSubmit={sendWord}>
          <input type="text" placeholder={isGameOver ? "게임 오버! 다시 시작하세요" : "단어를 입력하세요..."} value={message} onChange={(e) => setMessage(e.target.value)} disabled={isGameOver} />
          <button type="submit" disabled={isGameOver}>전송</button>
        </form>
      </div>
    );
  }

  return null;
}

export default App;
