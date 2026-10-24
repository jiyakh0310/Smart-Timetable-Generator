import { Link } from 'react-router-dom';

const cls = (variant, size, block, extra) =>
  `btn btn-${variant}${size === 'sm' ? ' btn-sm' : ''}${block ? ' btn-block' : ''}${extra ? ` ${extra}` : ''}`;

// variant: primary | secondary | ghost | danger     size: md | sm
export function Button({ variant = 'primary', size = 'md', block = false, loading = false, children, disabled, type = 'button', className, ...rest }) {
  return (
    <button type={type} className={cls(variant, size, block, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="btn-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ButtonLink({ variant = 'secondary', size = 'md', block = false, to, children, className, ...rest }) {
  return <Link to={to} className={cls(variant, size, block, className)} {...rest}>{children}</Link>;
}
