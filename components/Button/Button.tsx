import React from 'react';

const Button = ({ label, variant = 'primary' }) => {
  const styles = {
    primary: {
      backgroundColor: 'var(--ds-color-action-primary)',  // token correto
      color: 'var(--ds-color-text-primary)',
      padding: '8px 16px',
      borderRadius: '4px',
    }
  };
  return <button style={styles[variant]}>{label}</button>;
};

export default Button;
