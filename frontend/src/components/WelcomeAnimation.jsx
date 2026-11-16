import { useState, useEffect } from "react";
import "../styles/welcome.css";

const FULL_TEXT = "Welcome to Samir Jadhav's Personal & Professional Chatbot";

export default function WelcomeAnimation({ onComplete }) {
  const [displayedText, setDisplayedText] = useState("");
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayedText(FULL_TEXT.slice(0, i));
      if (i >= FULL_TEXT.length) {
        clearInterval(interval);
        // Wait a moment, then fade out
        setTimeout(() => setFadeOut(true), 800);
        setTimeout(() => onComplete(), 1600);
      }
    }, 45);
    return () => clearInterval(interval);
  }, [onComplete]);

  return (
    <div className={`welcome-overlay ${fadeOut ? "fade-out" : ""}`}>
      <div className="welcome-content">
        <div className="welcome-icon">🤖</div>
        <h1 className="welcome-text">
          {displayedText}
          <span className="cursor-blink">|</span>
        </h1>
      </div>
    </div>
  );
}
