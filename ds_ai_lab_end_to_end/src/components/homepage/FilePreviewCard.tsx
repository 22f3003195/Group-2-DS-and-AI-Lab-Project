import React, { useEffect, useState } from 'react';
import { FileText, X, ArrowRight } from 'lucide-react';
import Card from '../shared/Card';
import Button from '../shared/Button';

export interface FilePreviewCardProps {
  file: File;
  onRemove: () => void;
  onAnalyze: () => void;
  isLoading?: boolean;
}

export const FilePreviewCard: React.FC<FilePreviewCardProps> = ({
  file,
  onRemove,
  onAnalyze,
  isLoading = false
}) => {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    // Generate object URL for image previews
    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setPreviewUrl(null);
    }
  }, [file]);

  // Helper to format bytes to human readable sizes
  const formatBytes = (bytes: number, decimals = 1) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  return (
    <Card style={{ padding: 'var(--space-24)', display: 'flex', flexDirection: 'column', gap: 'var(--space-24)' }}>
      {/* File Info row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-12) var(--space-16)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-btn)',
        backgroundColor: 'rgba(0,0,0,0.01)',
        gap: 'var(--space-12)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-12)', overflow: 'hidden' }}>
          {previewUrl ? (
            <img
              src={previewUrl}
              alt="Lab report preview"
              style={{
                width: '44px',
                height: '44px',
                objectFit: 'cover',
                borderRadius: '8px',
                border: '1px solid var(--color-border)'
              }}
            />
          ) : (
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              backgroundColor: 'rgba(15, 110, 110, 0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--color-primary)',
              flexShrink: 0
            }}>
              <FileText size={20} />
            </div>
          )}
          
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', textAlign: 'left' }}>
            <span style={{
              fontWeight: 500,
              fontSize: '14px',
              color: 'var(--color-text-primary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: '220px'
            }}>
              {file.name}
            </span>
            <span className="caption" style={{ fontSize: '12px' }}>
              {formatBytes(file.size)}
            </span>
          </div>
        </div>

        <button
          className="btn btn--ghost"
          onClick={onRemove}
          disabled={isLoading}
          aria-label="Remove selected file"
          style={{ padding: '6px', borderRadius: '50%' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Action triggers */}
      <Button
        variant="primary"
        onClick={onAnalyze}
        isLoading={isLoading}
        style={{ width: '100%', justifyContent: 'center' }}
      >
        Analyze My Report <ArrowRight size={16} style={{ marginLeft: '6px' }} />
      </Button>
    </Card>
  );
};

export default FilePreviewCard;
