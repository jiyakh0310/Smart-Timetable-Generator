// Isha - R19: create (announcement = null) or edit an announcement. Admin only. Mount only while open so each use starts fresh.
import { useState } from 'react';
import { Button, Dialog, Notice, SelectField, TextAreaField, TextField, useToast } from '../../components/ui';
import { announcementsApi, CATEGORIES, LIMITS, toPayload, validateAnnouncement } from './announcements.js';

export default function AnnouncementFormDialog({ announcement, onClose, onSaved }) {
  const editing = Boolean(announcement);
  const toast = useToast();
  const [form, setForm] = useState({ title: announcement?.title ?? '', message: announcement?.message ?? '', category: announcement?.category ?? 'general' });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState('');
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  // `publish` is only used when creating: "Save as draft" or "Publish now".
  async function save(publish) {
    setFormError('');
    const clientErrors = validateAnnouncement(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;
    setBusy(publish ? 'publish' : 'save');
    try {
      const body = toPayload(form);
      const saved = editing ? await announcementsApi.update(announcement.id, body) : await announcementsApi.create({ ...body, publish });
      toast({
        tone: 'success',
        title: editing ? 'Announcement updated' : publish ? 'Announcement published' : 'Draft saved',
        message: saved.title,
      });
      onSaved(saved);
    } catch (err) {
      setErrors(err.details || {});
      setFormError(err.message);
      setBusy('');
    }
  }

  return (
    <Dialog open title={editing ? 'Edit announcement' : 'New announcement'} onClose={busy ? () => {} : onClose} wide initialFocus="first">
      <form className="form" noValidate onSubmit={(e) => { e.preventDefault(); save(false); }}>
        {formError && <Notice tone="danger">{formError}</Notice>}
        <TextField label="Title" value={form.title} onChange={set('title')} error={errors.title} maxLength={LIMITS.titleMax} placeholder="e.g. Mid-term exam schedule" />
        <SelectField label="Category" value={form.category} onChange={set('category')} error={errors.category}>
          {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </SelectField>
        <TextAreaField label="Announcement" value={form.message} onChange={set('message')} error={errors.message} rows={8} maxLength={LIMITS.messageMax}
          hint={`${form.message.length} / ${LIMITS.messageMax} characters. Plain text; blank lines start a new paragraph.`} />
        {editing && announcement.status === 'published' && <Notice tone="info">This announcement is published. Saved changes are visible to faculty and students straight away.</Notice>}
        {!editing && <Notice tone="info">A draft is visible to administrators only. Published announcements are visible to all faculty and students.</Notice>}
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose} disabled={Boolean(busy)}>Cancel</Button>
          {editing ? (
            <Button type="submit" loading={busy === 'save'}>Save changes</Button>
          ) : (
            <>
              <Button variant="secondary" type="submit" loading={busy === 'save'} disabled={busy === 'publish'}>Save as draft</Button>
              <Button onClick={() => save(true)} loading={busy === 'publish'} disabled={busy === 'save'}>Publish now</Button>
            </>
          )}
        </div>
      </form>
    </Dialog>
  );
}
