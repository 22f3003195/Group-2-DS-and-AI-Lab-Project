import { useState, useEffect } from 'react';
import { Shield, Zap, AlertCircle, Heart, Moon, Sun } from 'lucide-react';
import UploadDropzone from './components/homepage/UploadDropzone';
import FilePreviewCard from './components/homepage/FilePreviewCard';
import ProcessingPanel from './components/homepage/ProcessingPanel';
import ErrorCard from './components/homepage/ErrorCard';
import Button from './components/shared/Button';
import Modal from './components/shared/Modal';
import { analyzeReport, type AnalysisResponse } from './services/api';
import Dashboard from './components/dashboard/Dashboard';
import ChatWidget from './components/chat/ChatWidget';

type PageState = 'empty' | 'preview' | 'processing' | 'error' | 'dashboard';

// Group 2, as recorded in docs/milestone-*/Team-contribution.md.
const GROUP_MEMBERS = ['Bryan', 'Rajat', 'Ritwik', 'Samta', 'Shivendra'];

function App() {
  const [state, setState] = useState<PageState>('empty');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResponse | null>(null);
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [chatOpen, setChatOpen] = useState(false);
  const [isTeamOpen, setIsTeamOpen] = useState(false);

  // Multi-step progress states
  const [currentStepId, setCurrentStepId] = useState(1);
  const [stepStatuses, setStepStatuses] = useState<Record<number, 'done' | 'active' | 'upcoming'>>({
    1: 'upcoming',
    2: 'upcoming',
    3: 'upcoming',
    4: 'upcoming',
  });

  // Load and apply theme
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null;
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
    setTheme(initialTheme);
    document.documentElement.setAttribute('data-theme', initialTheme);
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem('theme', nextTheme);
  };

  const handleFileSelect = (file: File) => {
    // Validate file size and type immediately
    const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
    const maxSize = 10 * 1024 * 1024; // 10MB

    if (!validTypes.includes(file.type)) {
      setErrorMessage("That file type isn't supported — please upload a JPG, PNG, or PDF.");
      setState('error');
      return;
    }

    if (file.size > maxSize) {
      setErrorMessage("That file is too large — please upload something under 10MB.");
      setState('error');
      return;
    }

    setSelectedFile(file);
    setState('preview');
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setState('empty');
  };

  const handleAnalyze = async () => {
    console.log('--- handleAnalyze called, selectedFile:', selectedFile ? selectedFile.name : 'null');
    if (!selectedFile) return;

    setState('processing');
    setCurrentStepId(1);
    setStepStatuses({
      1: 'active',
      2: 'upcoming',
      3: 'upcoming',
      4: 'upcoming',
    });

    try {
      const result = await analyzeReport(selectedFile, (stepId, status) => {
        setCurrentStepId(stepId);
        setStepStatuses((prev) => ({
          ...prev,
          [stepId]: status,
        }));
      });

      setAnalysisResult(result);
      setState('dashboard');
    } catch (err: any) {
      console.error('Analysis error caught in App:', err);
      setErrorMessage(err.message || 'An error occurred during analysis.');
      setState('error');
    }
  };

  const handleRetry = () => {
    setSelectedFile(null);
    setState('empty');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--color-bg-app)' }}>
      {/* Navigation Header */}
      <header style={{
        borderBottom: '1px solid var(--color-border)',
        backgroundColor: 'var(--color-bg-card)',
        padding: '16px 0',
        transition: 'background-color 0.2s, border-color 0.2s'
      }}>
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-primary)' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(15, 110, 110, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Heart size={18} fill="var(--color-primary)" />
            </div>
            <span style={{ fontWeight: 700, fontSize: '20px', letterSpacing: '-0.5px', color: 'var(--color-text-primary)' }}>
              MedReport <span style={{ color: 'var(--color-primary)' }}>AI</span>
            </span>
          </div>

          {/* Right Navigation */}
          <nav style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-24)' }}>
            <a href="#how-it-works" style={{ textDecoration: 'none', color: 'var(--color-text-secondary)', fontSize: '14px', fontWeight: 500 }}>
              How it works
            </a>
            <button
              className="btn btn--ghost"
              onClick={toggleTheme}
              aria-label="Toggle theme"
              style={{ padding: '8px', borderRadius: '50%' }}
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <Button
              variant="secondary"
              style={{ padding: '8px 16px', fontSize: '14px' }}
              onClick={() => setIsTeamOpen(true)}
              aria-haspopup="dialog"
            >
              Group 2
            </Button>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 'var(--space-40) 0' }}>
        <div className="container" style={{ maxWidth: state === 'dashboard' ? '1140px' : '768px', display: 'flex', flexDirection: 'column', gap: 'var(--space-40)', transition: 'max-width 0.25s ease' }}>
          {state !== 'dashboard' ? (
            <>
              {/* Hero Section */}
              <section style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 'var(--space-16)' }}>
                <h1 className="h1">Understand your lab report in plain English.</h1>
                <p className="body-secondary" style={{ fontSize: '16px', maxWidth: '640px', margin: '0 auto' }}>
                   Upload a photo or PDF of your medical report and get an easy-to-read breakdown of every result — plus a chat assistant to answer your questions.
                </p>
                
                {/* Trust Row */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 'var(--space-16)',
                  marginTop: '8px',
                  color: 'var(--color-text-secondary)',
                  fontSize: '13px'
                }}>
                  <span className="flex-row"><Shield size={16} style={{ color: 'var(--color-primary)' }} /> 🔒 Private & secure</span>
                  <span className="flex-row"><Zap size={16} style={{ color: 'var(--color-secondary-accent)' }} /> ⚡ Results in a few minutes</span>
                  <span className="flex-row"><AlertCircle size={16} style={{ color: 'var(--color-status-unknown)' }} /> 🩺 Not a substitute for medical advice</span>
                </div>
              </section>

              {/* Dynamic State Card Wrapper */}
              <section>
                {state === 'empty' && (
                  <UploadDropzone onFileSelect={handleFileSelect} />
                )}
                {state === 'preview' && selectedFile && (
                  <FilePreviewCard
                    file={selectedFile}
                    onRemove={handleRemoveFile}
                    onAnalyze={handleAnalyze}
                  />
                )}
                {state === 'processing' && (
                  <ProcessingPanel
                    currentStepId={currentStepId}
                    stepStatuses={stepStatuses}
                  />
                )}
                {state === 'error' && (
                  <ErrorCard
                    message={errorMessage}
                    onRetry={handleRetry}
                    onUploadDifferent={handleRetry}
                  />
                )}
              </section>

              {/* How It Works Row */}
              <section id="how-it-works" style={{ borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-40)', marginTop: 'var(--space-24)' }}>
                <h2 className="h2" style={{ textAlign: 'center', marginBottom: 'var(--space-32)' }}>How it works</h2>
                <div className="grid-3" style={{ textAlign: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-12)' }}>
                    <div style={{ fontSize: '32px' }}>📤</div>
                    <h3 className="h3">1. Upload report</h3>
                    <p className="caption" style={{ maxWidth: '200px' }}>Upload your PDF document or snap a photo of your paper report.</p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-12)' }}>
                    <div style={{ fontSize: '32px' }}>🤖</div>
                    <h3 className="h3">2. AI reads & extracts</h3>
                    <p className="caption" style={{ maxWidth: '200px' }}>AI scans and categorizes your specific test parameters and values.</p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-12)' }}>
                    <div style={{ fontSize: '32px' }}>💬</div>
                    <h3 className="h3">3. Interactive breakdown</h3>
                    <p className="caption" style={{ maxWidth: '200px' }}>Read a plain-language summary and chat directly with your assistant.</p>
                  </div>
                </div>
              </section>
            </>
          ) : (
            analysisResult && (
              <Dashboard
                data={analysisResult}
                fileName={selectedFile ? selectedFile.name : 'medical_report.pdf'}
                onNewReport={handleRetry}
                onOpenChat={() => setChatOpen(true)}
              />
            )
          )}
        </div>
      </main>

      {/* Footer */}
      <footer style={{
        borderTop: '1px solid var(--color-border)',
        backgroundColor: 'var(--color-bg-card)',
        padding: '24px 0',
        textAlign: 'center',
        transition: 'background-color 0.2s, border-color 0.2s'
      }}>
        <div className="container" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <p className="caption" style={{ maxWidth: '600px', margin: '0 auto' }}>
            MedReport AI does not store your report longer than needed to generate your explanation. This tool provides general information only and is not a diagnosis or clinical recommendation.
          </p>
          <p className="caption" style={{ fontSize: '11px', opacity: 0.8 }}>
            &copy; {new Date().getFullYear()} MedReport AI. All rights reserved.
          </p>
        </div>
      </footer>

      {/* Floating Chat Widget */}
      <ChatWidget
        isOpen={chatOpen}
        onToggle={() => setChatOpen((prev) => !prev)}
        reportContext={analysisResult}
      />

      {/* Group 2 team modal */}
      <Modal
        isOpen={isTeamOpen}
        onClose={() => setIsTeamOpen(false)}
        title="Group 2"
      >
        <p className="body-secondary" style={{ marginTop: 0, marginBottom: 'var(--space-16)' }}>
          Built by five students for the IIT&nbsp;Madras DS/AI Lab.
        </p>
        <ul
          data-testid="group-members"
          style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}
        >
          {GROUP_MEMBERS.map((name) => (
            <li
              key={name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '10px 12px',
                borderRadius: '8px',
                backgroundColor: 'var(--color-bg-app)',
                border: '1px solid var(--color-border)'
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: '30px',
                  height: '30px',
                  flexShrink: 0,
                  borderRadius: '50%',
                  backgroundColor: 'rgba(15, 110, 110, 0.12)',
                  color: 'var(--color-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '13px'
                }}
              >
                {name.charAt(0)}
              </span>
              <span style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>{name}</span>
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  );
}

export default App;
