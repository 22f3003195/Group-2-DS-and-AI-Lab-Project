import React, { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import Button from '../shared/Button';

export interface UploadDropzoneProps {
  onFileSelect: (file: File) => void;
}

export const UploadDropzone: React.FC<UploadDropzoneProps> = ({ onFileSelect }) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  const onButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      onButtonClick();
    }
  };

  // Custom styling dynamically applied on dragover
  const dropzoneStyles: React.CSSProperties = {
    border: '2px dashed var(--color-primary)',
    borderRadius: 'var(--radius-card)',
    padding: 'var(--space-40) var(--space-24)',
    textAlign: 'center',
    cursor: 'pointer',
    backgroundColor: isDragActive ? 'rgba(15, 110, 110, 0.08)' : 'rgba(15, 110, 110, 0.02)',
    transition: 'all 0.2s ease',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-16)',
    outline: 'none',
  };

  return (
    <div
      style={dropzoneStyles}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={onButtonClick}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="button"
      aria-label="Upload medical report dropzone. Drag and drop PDF or images here, or press enter to browse."
    >
      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".jpg,.jpeg,.png,.pdf,image/png,image/jpeg,application/pdf"
        onChange={handleFileInputChange}
        data-testid="file-input"
      />
      
      <div style={{
        width: '56px',
        height: '56px',
        borderRadius: '50%',
        backgroundColor: 'rgba(15, 110, 110, 0.1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--color-primary)'
      }}>
        <Upload size={28} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <p style={{ fontWeight: 600, fontSize: '18px', color: 'var(--color-text-primary)' }}>
          Drag & drop your report here
        </p>
        <p className="caption">
          or click to browse — JPG, PNG, or PDF, up to 10MB
        </p>
      </div>

      <Button
        variant="secondary"
        type="button"
        onClick={(e) => {
          e.stopPropagation(); // prevent triggering parent div onClick
          onButtonClick();
        }}
        tabIndex={-1} /* handled by parent container */
        style={{ marginTop: '8px' }}
      >
        Choose File
      </Button>
    </div>
  );
};

export default UploadDropzone;
