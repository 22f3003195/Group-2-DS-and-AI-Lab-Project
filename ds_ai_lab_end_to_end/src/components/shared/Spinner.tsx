import React from 'react';

export interface SpinnerProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  color?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({
  size = 24,
  color = 'currentColor',
  className = '',
  ...props
}) => {
  return (
    <svg
      className={`spinner ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <circle cx="12" cy="12" r="10" opacity="0.25" style={{ stroke: 'var(--color-border)' }} />
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  );
};

export default Spinner;
