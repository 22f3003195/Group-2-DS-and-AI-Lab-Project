import React from 'react';
import { FileText, CheckCircle2, Circle } from 'lucide-react';
import Card from '../shared/Card';

export interface ProcessingPanelProps {
  currentStepId: number; // 1 to 4
  stepStatuses: Record<number, 'done' | 'active' | 'upcoming'>;
}

export const ProcessingPanel: React.FC<ProcessingPanelProps> = ({
  currentStepId,
  stepStatuses
}) => {
  const steps = [
    { id: 1, text: 'Extracting text (OCR)' },
    { id: 2, text: 'Identifying your test results (AI)' },
    { id: 3, text: 'Organizing your results' },
    { id: 4, text: 'Writing your plain-language explanation' }
  ];

  // Calculate percentage based on current step ID
  const percentComplete = Math.min(((currentStepId - 1) / steps.length) * 100 + 10, 95);

  // Determine current headline text based on step
  const getHeadline = () => {
    switch (currentStepId) {
      case 1:
        return 'Reading your report...';
      case 2:
        return 'Extracting test values...';
      case 3:
        return 'Organizing results...';
      case 4:
        return 'Writing plain-language explanation...';
      default:
        return 'Processing your report...';
    }
  };

  return (
    <Card style={{ padding: 'var(--space-32) var(--space-24)', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 'var(--space-24)' }}>
      {/* Animated icon indicator */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '8px' }}>
        <div 
          style={{
            position: 'relative',
            width: '72px',
            height: '72px',
            borderRadius: '50%',
            backgroundColor: 'rgba(15, 110, 110, 0.05)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-primary)',
          }}
          data-testid="animated-loader"
        >
          {/* Looping pulse animation ring */}
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            borderRadius: '50%',
            border: '2px solid var(--color-primary)',
            animation: 'pulseRing 1.5s cubic-bezier(0.215, 0.61, 0.355, 1) infinite',
            opacity: 0.6
          }} />
          
          <FileText size={32} style={{ animation: 'bounceSlow 2s ease-in-out infinite' }} />
        </div>
      </div>

      <div>
        <h3 className="h3" style={{ marginBottom: '8px' }}>
          {getHeadline()}
        </h3>
        <p className="caption" style={{ margin: '0 auto', maxWidth: '340px' }}>
          This usually takes 20–60 seconds. Please don't close this tab.
        </p>
      </div>

      {/* Progress Bar */}
      <div style={{
        width: '100%',
        height: '6px',
        backgroundColor: 'var(--color-border)',
        borderRadius: '3px',
        overflow: 'hidden',
        position: 'relative'
      }}>
        <div style={{
          width: `${percentComplete}%`,
          height: '100%',
          backgroundColor: 'var(--color-primary)',
          borderRadius: '3px',
          transition: 'width 0.4s ease-in-out'
        }} />
      </div>

      {/* Stepper Steps */}
      <div style={{ display: 'flex', flexDirection: 'column', alignSelf: 'center', width: '100%', maxWidth: '340px', gap: 'var(--space-16)', textAlign: 'left', marginTop: '8px' }}>
        {steps.map((step) => {
          const status = stepStatuses[step.id] || 'upcoming';
          const isDone = status === 'done';
          const isActive = status === 'active';
          
          let iconColor = 'var(--color-status-unknown)';
          let textColor = 'var(--color-text-secondary)';
          let fontWeight = 400;

          if (isDone) {
            iconColor = 'var(--color-primary)';
            textColor = 'var(--color-text-primary)';
          } else if (isActive) {
            iconColor = 'var(--color-secondary-accent)';
            textColor = 'var(--color-text-primary)';
            fontWeight = 500;
          }

          return (
            <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-12)' }} data-testid={`step-${step.id}`}>
              <div style={{ color: iconColor, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                {isDone ? (
                  <CheckCircle2 size={20} fill="rgba(15, 110, 110, 0.1)" />
                ) : isActive ? (
                  <div style={{ position: 'relative', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: 'var(--color-secondary-accent)',
                      animation: 'pulseDot 1.2s infinite ease-in-out'
                    }} />
                    <Circle size={20} style={{ position: 'absolute', opacity: 0.4 }} />
                  </div>
                ) : (
                  <Circle size={20} />
                )}
              </div>
              <span style={{ fontSize: '15px', color: textColor, fontWeight }}>
                {step.text}
              </span>
            </div>
          );
        })}
      </div>

      {/* Keyframe animations styles injection */}
      <style>{`
        @keyframes pulseRing {
          0% { transform: scale(0.95); opacity: 0.8; }
          100% { transform: scale(1.3); opacity: 0; }
        }
        @keyframes pulseDot {
          0%, 100% { transform: scale(0.8); opacity: 0.6; }
          50% { transform: scale(1.3); opacity: 1; }
        }
        @keyframes bounceSlow {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
        }
      `}</style>
    </Card>
  );
};

export default ProcessingPanel;
