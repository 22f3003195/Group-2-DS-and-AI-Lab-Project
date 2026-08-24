import React from 'react';

export type BadgeStatus = 'HIGH' | 'LOW' | 'NORMAL' | 'UNKNOWN';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  status: BadgeStatus;
  /** Plain-language reason shown when status is UNKNOWN. */
  reason?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  status,
  reason,
  className = '',
  ...props
}) => {
  const statusLower = status.toLowerCase();
  const badgeClass = `badge--${statusLower}`;
  // "UNKNOWN" reads as a system failure. "NOT CHECKED" plus the reason tells
  // the patient the truth: we declined to judge this one, and why.
  const label = status === 'UNKNOWN' ? 'NOT CHECKED' : status;

  return (
    <span
      className={`badge ${badgeClass} ${className}`.trim()}
      title={status === 'UNKNOWN' && reason ? reason : undefined}
      {...props}
    >
      <span className="badge-dot" aria-hidden="true" />
      {label}
    </span>
  );
};

export default Badge;
