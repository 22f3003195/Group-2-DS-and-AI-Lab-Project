import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  elevated?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  interactive = false,
  elevated = false,
  className = '',
  ...props
}) => {
  const interactiveClass = interactive ? 'card--interactive' : '';
  const elevatedStyle = elevated ? { boxShadow: 'var(--shadow-elevated)' } : {};

  return (
    <div
      className={`card ${interactiveClass} ${className}`.trim()}
      style={elevatedStyle}
      {...props}
    >
      {children}
    </div>
  );
};

export default Card;
