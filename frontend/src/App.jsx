import { useState, useCallback } from "react";
import WelcomeAnimation from "./components/WelcomeAnimation";
import ChatBox from "./components/ChatBox";
import "./App.css";

function App() {
  const [showWelcome, setShowWelcome] = useState(true);

  const handleWelcomeComplete = useCallback(() => {
    setShowWelcome(false);
  }, []);

  return (
    <div className="app">
      {showWelcome && <WelcomeAnimation onComplete={handleWelcomeComplete} />}
      {!showWelcome && <ChatBox />}
    </div>
  );
}

export default App;
