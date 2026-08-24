import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import App from '../App';
import UploadDropzone from '../components/homepage/UploadDropzone';
import FilePreviewCard from '../components/homepage/FilePreviewCard';
import ProcessingPanel from '../components/homepage/ProcessingPanel';
import ErrorCard from '../components/homepage/ErrorCard';

describe('UploadDropzone Component', () => {
  it('renders instructions and button', () => {
    const handleFileSelect = vi.fn();
    render(<UploadDropzone onFileSelect={handleFileSelect} />);
    expect(screen.getByText(/drag & drop your report here/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /choose file/i })).toBeInTheDocument();
  });

  it('selects file through hidden input change', () => {
    const handleFileSelect = vi.fn();
    render(<UploadDropzone onFileSelect={handleFileSelect} />);
    
    const file = new File(['dummy content'], 'report.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input');
    
    fireEvent.change(input, { target: { files: [file] } });
    expect(handleFileSelect).toHaveBeenCalledWith(file);
  });
});

describe('FilePreviewCard Component', () => {
  const dummyFile = new File(['dummy content'], 'test-report.pdf', { type: 'application/pdf' });

  it('renders file info and size correctly', () => {
    const handleRemove = vi.fn();
    const handleAnalyze = vi.fn();
    render(
      <FilePreviewCard
        file={dummyFile}
        onRemove={handleRemove}
        onAnalyze={handleAnalyze}
      />
    );

    expect(screen.getByText('test-report.pdf')).toBeInTheDocument();
    expect(screen.getByText(/analyze my report/i)).toBeInTheDocument();
  });

  it('calls onRemove and onAnalyze triggers', () => {
    const handleRemove = vi.fn();
    const handleAnalyze = vi.fn();
    render(
      <FilePreviewCard
        file={dummyFile}
        onRemove={handleRemove}
        onAnalyze={handleAnalyze}
      />
    );

    fireEvent.click(screen.getByLabelText(/remove selected file/i));
    expect(handleRemove).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /analyze my report/i }));
    expect(handleAnalyze).toHaveBeenCalledTimes(1);
  });
});

describe('ProcessingPanel Component', () => {
  it('renders list of pipeline steps', () => {
    const stepStatuses: Record<number, 'done' | 'active' | 'upcoming'> = {
      1: 'done',
      2: 'active',
      3: 'upcoming',
      4: 'upcoming'
    };
    render(<ProcessingPanel currentStepId={1} stepStatuses={stepStatuses} />);

    expect(screen.getByText('Reading your report...')).toBeInTheDocument();
    expect(screen.getByText('Extracting text (OCR)')).toBeInTheDocument();
    expect(screen.getByText('Identifying your test results (AI)')).toBeInTheDocument();
  });
});

describe('ErrorCard Component', () => {
  it('renders unsupported type error states', () => {
    const handleRetry = vi.fn();
    render(<ErrorCard message="That file type isn't supported" onRetry={handleRetry} />);

    expect(screen.getByText('Unsupported File Type')).toBeInTheDocument();
    expect(screen.getByText("That file type isn't supported")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('triggers onRetry callback', () => {
    const handleRetry = vi.fn();
    render(<ErrorCard message="OCR failure" onRetry={handleRetry} />);

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(handleRetry).toHaveBeenCalledTimes(1);
  });
});

describe('App Flow Integration', () => {
  it('renders landing page by default', () => {
    render(<App />);
    expect(screen.getByText(/understand your lab report in plain english/i)).toBeInTheDocument();
    expect(screen.getByText(/drag & drop your report here/i)).toBeInTheDocument();
  });

  it('shows error state for invalid file type', async () => {
    render(<App />);
    const file = new File(['dummy content'], 'report.txt', { type: 'text/plain' });
    const input = screen.getByTestId('file-input');

    fireEvent.change(input, { target: { files: [file] } });
    
    expect(screen.getByText('Unsupported File Type')).toBeInTheDocument();
    expect(screen.getByText(/isn't supported/i)).toBeInTheDocument();
  });

  it('shows error state for oversized files', async () => {
    render(<App />);
    // Create 11MB file (greater than 10MB)
    const largeFile = new File([new ArrayBuffer(11 * 1024 * 1024)], 'huge.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input');

    fireEvent.change(input, { target: { files: [largeFile] } });
    
    expect(screen.getByText('File Too Large')).toBeInTheDocument();
    expect(screen.getByText(/upload something under 10mb/i)).toBeInTheDocument();
  });

  it('progresses to preview, processing, and success views', async () => {
    render(<App />);
    const file = new File(['dummy content'], 'report.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('file-input');

    // 1. Move to preview
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /analyze my report/i })).toBeInTheDocument();

    // 2. Click Analyze to trigger processing
    fireEvent.click(screen.getByRole('button', { name: /analyze my report/i }));

    // 3. Wait for progress simulation to complete (mock takes ~6.5 seconds total)
    // We adjust vitest timer mocks or use longer timeout
    await waitFor(() => {
      expect(screen.getByText(/outside the normal range/i)).toBeInTheDocument();
    }, { timeout: 8000 });

    expect(screen.getByText('Total Tests')).toBeInTheDocument();
  }, 12000);
});

describe('Group 2 header button', () => {
  it('replaces Sign In and opens a modal listing every member first name', () => {
    render(<App />);

    // The Sign In control is gone.
    expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument();

    const groupBtn = screen.getByRole('button', { name: /group 2/i });
    expect(groupBtn).toBeInTheDocument();

    // Modal is closed until asked for.
    expect(screen.queryByTestId('group-members')).not.toBeInTheDocument();

    fireEvent.click(groupBtn);

    const list = screen.getByTestId('group-members');
    expect(list).toBeInTheDocument();
    const names = Array.from(list.querySelectorAll('li')).map(li => li.textContent);
    // First names only, one entry per member of Group 2.
    expect(names).toHaveLength(5);
    ['Bryan', 'Rajat', 'Ritwik', 'Samta', 'Shivendra'].forEach(first => {
      expect(names.some(n => n?.includes(first))).toBe(true);
    });
    // No surnames leaked in.
    expect(list.textContent).not.toMatch(/Trivedi|Srivastava|Ranka|Robinson/i);
  });

  it('closes the modal on Escape', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /group 2/i }));
    expect(screen.getByTestId('group-members')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('group-members')).not.toBeInTheDocument();
  });
});
