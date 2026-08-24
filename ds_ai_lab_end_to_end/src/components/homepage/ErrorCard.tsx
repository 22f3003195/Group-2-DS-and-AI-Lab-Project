import React from 'react';
import { AlertCircle } from 'lucide-react';
import Card from '../shared/Card';
import Button from '../shared/Button';

export interface ErrorCardProps {
  message: string;
  onRetry: () => void;
  onUploadDifferent?: () => void;
}

export const ErrorCard: React.FC<ErrorCardProps> = ({
  message,
  onRetry,
  onUploadDifferent
}) => {
  // Determine if it is a file type or file size error to display a relevant heading
  const getErrorHeading = () => {
    if (message.toLowerCase().includes('type')) {
      return 'Unsupported File Type';
    }
    if (message.toLowerCase().includes('large') || message.toLowerCase().includes('10mb')) {
      return 'File Too Large';
    }
    if (message.toLowerCase().includes('read') || message.toLowerCase().includes('ocr')) {
      return 'Reading Failed';
    }
    return 'Analysis Error';
  };

  const getTip = () => {
    if (message.toLowerCase().includes('type')) {
      return 'Please make sure you are uploading a JPG, PNG image or a PDF document.';
    }
    if (message.toLowerCase().includes('large')) {
      return 'Try compressing your file, or exporting a smaller version of the lab report PDF.';
    }
    return 'Try a clearer photo with good lighting, or upload a PDF export from your lab\'s patient portal instead.';
  };

  return (
    <Card style={{ padding: 'var(--space-32) var(--space-24)', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 'var(--space-24)' }}>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          backgroundColor: 'var(--color-status-low-bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-status-low)'
        }}>
          <AlertCircle size={28} />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h3 className="h3" style={{ color: 'var(--color-text-primary)' }}>
          {getErrorHeading()}
        </h3>
        <p className="body-text" style={{ fontSize: '14px', color: 'var(--color-status-high)', fontWeight: 500 }}>
          {message}
        </p>
        <p className="caption" style={{ margin: 'var(--space-8) auto 0', maxWidth: '380px' }}>
          {getTip()}
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-12)', marginTop: '8px' }}>
        <Button
          variant="primary"
          onClick={onRetry}
          style={{ width: '100%', justifyContent: 'center' }}
        >
          Try Again
        </Button>
        
        {onUploadDifferent && (
          <button
            className="btn btn--ghost"
            onClick={onUploadDifferent}
            style={{ width: '100%', justifyContent: 'center', textDecoration: 'underline' }}
          >
            Upload a different file
          </button>
        )}
      </div>
    </Card>
  );
};

export default ErrorCard;
