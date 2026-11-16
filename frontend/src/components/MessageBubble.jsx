import "../styles/message.css";

export default function MessageBubble({ role, content }) {
  const isUser = role === "user";

  return (
    <div className={`message-row ${isUser ? "user-row" : "bot-row"}`}>
      {!isUser && <div className="bot-avatar">🤖</div>}
      <div className={`message-bubble ${isUser ? "user-bubble" : "bot-bubble"}`}>
        {content}
      </div>
    </div>
  );
}
