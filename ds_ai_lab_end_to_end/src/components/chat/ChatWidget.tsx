import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Send, AlertCircle, RefreshCw, Bot } from 'lucide-react';
import Button from '../shared/Button';
import Spinner from '../shared/Spinner';
import { sendChatMessage, type ChatMessage, type AnalysisResponse } from '../../services/api';

export interface ChatWidgetProps {
  isOpen: boolean;
  onToggle: () => void;
  reportContext: AnalysisResponse | null;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({
  isOpen,
  onToggle,
  reportContext
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of conversation
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, isGenerating, errorMsg]);

  // Seed initial greeting when reportContext is available or changes
  useEffect(() => {
    // Built from the actual report. The previous version interpolated a real
    // abnormal_count but then named Hemoglobin / Platelets / Cholesterol /
    // Vitamin D literally - the six tests from the mock fixture - so patients
    // were told those were their abnormal results whatever they uploaded.
    const buildGreeting = (ctx: AnalysisResponse): string => {
      const abnormal = ctx.lab_results.filter(r => r.status === 'HIGH' || r.status === 'LOW');
      const unknown = ctx.lab_results.filter(r => r.status === 'UNKNOWN');
      const names = (rs: typeof abnormal) => rs.map(r => r.test_name).join(', ');

      let text = "Hello! I am your MedReport AI Assistant. I've read your report.\n\n";
      if (abnormal.length > 0) {
        text += `**${abnormal.length} result${abnormal.length === 1 ? '' : 's'} ${
          abnormal.length === 1 ? 'is' : 'are'} outside the normal range** (${names(abnormal)}).`;
      } else {
        text += 'Every result we could check is **within its normal range**.';
      }
      if (unknown.length > 0) {
        text += ` ${unknown.length} result${unknown.length === 1 ? '' : 's'} (${names(unknown)}) ` +
                `could not be checked against our reference table.`;
      }
      text += '\n\nAsk me about any of them, or tell me how you have been feeling.';
      return text;
    };

    const greetingText = reportContext
      ? buildGreeting(reportContext)
      : "Hello! I am your MedReport AI Assistant. Please upload your medical report on the main screen, and I'll be happy to translate your lab parameters and explain reference ranges.";

    setMessages([
      {
        id: 'greeting',
        sender: 'assistant',
        text: greetingText,
        timestamp: new Date()
      }
    ]);
  }, [reportContext]);

  // Quick replies derived from THIS report, not from the mock fixture.
  const quickReplies = (() => {
    if (!reportContext) {
      return [
        'What is Hemoglobin?',
        'How do reference ranges work?',
        'What files can I upload?'
      ];
    }
    const abnormal = reportContext.lab_results.filter(r => r.status === 'HIGH' || r.status === 'LOW');
    const unknown = reportContext.lab_results.filter(r => r.status === 'UNKNOWN');
    const replies = abnormal.slice(0, 2).map(
      r => `Explain my ${r.status.toLowerCase()} ${r.test_name}`
    );
    if (unknown.length > 0) {
      replies.push(`Why couldn't you check my ${unknown[0].test_name}?`);
    }
    if (abnormal.length === 0) {
      replies.unshift('Are all my results normal?');
    }
    // The assigned two-way task: invite the patient to volunteer symptoms.
    replies.push('I want to tell you a symptom');
    return replies.slice(0, 4);
  })();

  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isGenerating) return;

    // Clear previous error
    setErrorMsg(null);
    setLastFailedMessage(null);

    const userMsg: ChatMessage = {
      id: Math.random().toString(),
      sender: 'user',
      text: text.trim(),
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setIsGenerating(true);

    try {
      // The greeting is UI chrome, not conversation. Sending it made the
      // history start with an assistant turn, which BioMistral's chat template
      // rejects outright ("Conversation roles must alternate"), so every
      // generation threw and silently fell back to the rule-based responder.
      const conversationHistory = messages.filter(m => m.id !== 'greeting');
      const responseText = await sendChatMessage(text, conversationHistory, reportContext || undefined);
      
      const assistantMsg: ChatMessage = {
        id: Math.random().toString(),
        sender: 'assistant',
        text: responseText,
        timestamp: new Date()
      };
      
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setLastFailedMessage(text);
      setErrorMsg(err.message || 'Something went wrong. Please check your network.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSendMessage(inputValue);
  };

  const handleRetry = () => {
    if (lastFailedMessage) {
      handleSendMessage(lastFailedMessage);
    }
  };

  // Helper to parse simple markdown bold tags **
  // Render **bold** and *italic*, and drop any marker that was left unbalanced.
  // The model emits summary-style formatting even for one-line answers, often
  // malformed - "* **An ion gap is ... clinician.*" matched nothing under the
  // old balanced-only split, so the raw asterisks were shown to the patient.
  const parseMessageText = (text: string) => {
    const cleaned = text
      .replace(/^\s*[*\-\u2022]\s+/gm, '')   // stray leading bullets
      .replace(/^#{1,6}\s*/gm, '');            // stray headings

    const parts = cleaned.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return <strong key={index} style={{ fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
        return <em key={index}>{part.slice(1, -1)}</em>;
      }
      // Anything left is plain text; remove markers that never found a pair.
      return part.replace(/\*+/g, '');
    });
  };

  return (
    <>
      {/* Floating Action Button (FAB) */}
      <button
        onClick={onToggle}
        className="btn"
        style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          backgroundColor: 'var(--color-primary)',
          color: '#FFFFFF',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 'var(--shadow-elevated)',
          border: 'none',
          cursor: 'pointer',
          zIndex: 999,
          transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          outline: 'none'
        }}
        aria-label={isOpen ? 'Close chat assistant' : 'Open chat assistant'}
        data-testid="chat-fab"
      >
        {isOpen ? <X size={24} /> : <MessageSquare size={24} />}
      </button>

      {/* Collapsible Chat Panel Overlay */}
      <div
        style={{
          position: 'fixed',
          bottom: '96px',
          right: '24px',
          width: '380px',
          maxWidth: 'calc(100vw - 48px)',
          height: '540px',
          maxHeight: 'calc(100vh - 140px)',
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-elevated)',
          display: isOpen ? 'flex' : 'none',
          flexDirection: 'column',
          overflow: 'hidden',
          zIndex: 998,
          animation: 'slideUp 0.25s ease-out'
        }}
        data-testid="chat-panel"
      >
        {/* Chat Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 20px',
          borderBottom: '1px solid var(--color-border)',
          backgroundColor: 'var(--color-bg-app)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              backgroundColor: 'rgba(15, 110, 110, 0.1)',
              color: 'var(--color-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Bot size={18} />
            </div>
            <div style={{ textAlign: 'left' }}>
              <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--color-text-primary)', display: 'block', lineHeight: '18px' }}>
                AI Medical Assistant
              </span>
              <span style={{ fontSize: '11px', color: 'var(--color-status-normal)', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-status-normal)' }} /> Online & ready
              </span>
            </div>
          </div>
          <button
            onClick={onToggle}
            className="btn btn--ghost"
            style={{ padding: '4px', borderRadius: '50%' }}
            aria-label="Minimize panel"
          >
            <X size={18} />
          </button>
        </div>

        {/* Messages Body */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          backgroundColor: 'var(--color-bg-card)'
        }} data-testid="chat-messages-container">
          
          {messages.map((msg) => {
            const isAssistant = msg.sender === 'assistant';
            return (
              <div
                key={msg.id}
                style={{
                  alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                  maxWidth: '85%',
                  textAlign: 'left'
                }}
                data-testid={isAssistant ? 'assistant-bubble' : 'user-bubble'}
              >
                <div style={{
                  padding: '12px 16px',
                  borderRadius: '16px',
                  borderTopLeftRadius: isAssistant ? '4px' : '16px',
                  borderBottomRightRadius: isAssistant ? '16px' : '4px',
                  backgroundColor: isAssistant ? 'var(--color-bg-app)' : 'var(--color-primary)',
                  color: isAssistant ? 'var(--color-text-primary)' : '#FFFFFF',
                  fontSize: '14px',
                  lineHeight: '20px',
                  whiteSpace: 'pre-wrap',
                  boxShadow: isAssistant ? 'none' : '0 2px 4px rgba(15, 110, 110, 0.15)',
                  border: isAssistant ? '1px solid var(--color-border)' : 'none'
                }}>
                  {parseMessageText(msg.text)}
                </div>
              </div>
            );
          })}

          {/* Typing Indicator dots */}
          {isGenerating && (
            <div style={{ alignSelf: 'flex-start', display: 'flex', gap: '4px', padding: '12px 16px', borderRadius: '16px', borderTopLeftRadius: '4px', backgroundColor: 'var(--color-bg-app)', border: '1px solid var(--color-border)' }} data-testid="typing-indicator">
              <span className="dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-text-secondary)', animation: 'bounceDot 1.4s infinite ease-in-out', animationDelay: '0s' }} />
              <span className="dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-text-secondary)', animation: 'bounceDot 1.4s infinite ease-in-out', animationDelay: '0.2s' }} />
              <span className="dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-text-secondary)', animation: 'bounceDot 1.4s infinite ease-in-out', animationDelay: '0.4s' }} />
            </div>
          )}

          {/* API Error Box */}
          {errorMsg && (
            <div style={{
              alignSelf: 'stretch',
              backgroundColor: 'rgba(217, 83, 79, 0.05)',
              border: '1px solid rgba(217, 83, 79, 0.2)',
              borderRadius: 'var(--radius-btn)',
              padding: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              alignItems: 'center',
              textAlign: 'center'
            }} data-testid="chat-error">
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--color-status-high)', fontSize: '13px', fontWeight: 600 }}>
                <AlertCircle size={14} /> Connection issue
              </div>
              <p className="caption" style={{ fontSize: '12px', margin: 0 }}>{errorMsg}</p>
              <button 
                onClick={handleRetry} 
                className="btn btn--secondary flex-row" 
                style={{ padding: '4px 12px', fontSize: '12px', border: '1px solid var(--color-border)', width: 'auto' }}
              >
                <RefreshCw size={10} /> Retry question
              </button>
            </div>
          )}

          {/* Quick Replies chips (render when not generating/error) */}
          {!isGenerating && !errorMsg && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }} data-testid="quick-replies">
              {quickReplies.map((reply, i) => (
                <button
                  key={i}
                  onClick={() => handleSendMessage(reply)}
                  className="btn btn--secondary"
                  style={{
                    padding: '8px 12px',
                    fontSize: '12px',
                    borderRadius: '12px',
                    border: '1px solid var(--color-border)',
                    textAlign: 'left',
                    color: 'var(--color-text-primary)',
                    backgroundColor: 'var(--color-bg-card)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                >
                  💡 {reply}
                </button>
              ))}
            </div>
          )}

          {/* Scroll bottom anchor */}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Form area */}
        <form 
          onSubmit={handleFormSubmit}
          style={{
            padding: '16px 20px',
            borderTop: '1px solid var(--color-border)',
            backgroundColor: 'var(--color-bg-app)'
          }}
        >
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask a question about your report..."
              className="form-input"
              style={{ flex: 1, paddingTop: '10px', paddingBottom: '10px', borderRadius: '20px', fontSize: '13px' }}
              disabled={isGenerating}
              data-testid="chat-input"
            />
            <button
              type="submit"
              className="btn"
              disabled={!inputValue.trim() || isGenerating}
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                backgroundColor: inputValue.trim() && !isGenerating ? 'var(--color-primary)' : 'var(--color-border)',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: 'none',
                cursor: inputValue.trim() && !isGenerating ? 'pointer' : 'default',
                padding: 0
              }}
              aria-label="Send message"
              data-testid="chat-send-btn"
            >
              {isGenerating ? <Spinner size={16} /> : <Send size={16} />}
            </button>
          </div>

          {/* Persistent advice disclaimer */}
          <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', textAlign: 'center', marginTop: '10px', lineHeight: '14px' }}>
            🛡️ AI guidance is not a diagnosis. Discuss with your doctor.
          </div>
        </form>
      </div>

      {/* Slide animation classes */}
      <style>{`
        @keyframes slideUp {
          from { transform: translateY(20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        @keyframes bounceDot {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
      `}</style>
    </>
  );
};

export default ChatWidget;
