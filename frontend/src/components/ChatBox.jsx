import { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";
import InputBar from "./InputBar";
import PlaceholderMessage from "./PlaceholderMessage";
import "../styles/chatbox.css";

const RAW_API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_URL = RAW_API_URL.replace(/\/+$/, "");

export default function ChatBox() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (text) => {
    const userMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || `Server returned status ${res.status}`);
      }

      const data = await res.json();
      const botMessage = { role: "bot", content: data.answer || "No response received." };
      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      const errorMessage = {
        role: "bot",
        content:
          err.message && !err.message.includes("Failed to fetch") && !err.message.includes("NetworkError")
            ? `⚠️ ${err.message}`
            : "⚠️ Unable to reach the server. If the backend is hosted on Render's free tier, it may be waking up from sleep (~30-50s). Please try sending your question again in a moment!",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chatbox-wrapper">
      <div className="chatbox-header">
        <span className="header-icon">🤖</span>
        <div className="header-text">
          <h2>Samir Jadhav</h2>
          <span className="header-subtitle">AI-Powered Personal Chatbot</span>
        </div>
      </div>

      <div className="chatbox-body">
        {messages.length === 0 && <PlaceholderMessage />}
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} role={msg.role} content={msg.content} />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      <InputBar onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
