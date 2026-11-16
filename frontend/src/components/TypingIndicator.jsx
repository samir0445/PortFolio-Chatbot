import "../styles/message.css";

export default function TypingIndicator() {
  return (
    <div className="message-row bot-row">
      <div className="bot-avatar">🤖</div>
      <div className="message-bubble bot-bubble typing-indicator">
        <span className="dot"></span>
        <span className="dot"></span>
        <span className="dot"></span>
      </div>
    </div>
  );
}
