import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginForm from './LoginForm.jsx';

const login = vi.fn();
vi.mock('../../app/AuthContext.jsx', () => ({ useAuth: () => ({ login }) }));

const renderForm = () =>
  render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginForm />} />
        <Route path="/admin" element={<p>admin home</p>} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => { login.mockReset(); });

describe('LoginForm (ISH-TC01..03)', () => {
  it('blocks empty submission, names the missing fields, and does not call the API', async () => {
    renderForm();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(login).not.toHaveBeenCalled();
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
  });

  it('signs in and goes to the role home', async () => {
    login.mockResolvedValue({ role: 'admin' });
    renderForm();
    await userEvent.type(screen.getByLabelText('Email'), 'admin@timetable.test');
    await userEvent.type(screen.getByLabelText('Password'), 'secret-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(login).toHaveBeenCalledWith('admin@timetable.test', 'secret-pass');
    expect(await screen.findByText('admin home')).toBeInTheDocument();
  });

  it('shows the server error message when credentials are wrong and re-enables the button', async () => {
    login.mockRejectedValue(Object.assign(new Error('Invalid email or password.'), { details: {} }));
    renderForm();
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.test');
    await userEvent.type(screen.getByLabelText('Password'), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });
});
