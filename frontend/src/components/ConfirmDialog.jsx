import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, Paper, Stack, Text, TextInput } from "@mantine/core";
import { IconAlertTriangle, IconChevronLeft, IconInfoCircle, IconShieldCheck, IconX } from "@tabler/icons-react";

export const CONFIRM_TONE_COLORS = { danger: "red", caution: "orange", safe: "teal" };

export function ConfirmNote({ tone = "neutral", children }) {
  if (tone === "neutral") {
    return (
      <Paper bg="var(--mantine-color-default-hover)" p="sm" radius="md" withBorder>
        <Group gap="xs" wrap="nowrap" align="flex-start">
          <IconInfoCircle size={18} color="var(--mantine-color-gray-6)" style={{ flexShrink: 0 }} aria-hidden="true" />
          <Text size="sm">{children}</Text>
        </Group>
      </Paper>
    );
  }
  const icon = tone === "safe" ? <IconShieldCheck size={18} /> : <IconAlertTriangle size={18} />;
  return <Alert color={CONFIRM_TONE_COLORS[tone] || "gray"} icon={icon}>{children}</Alert>;
}

export function ConfirmItem({ name, detail }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Text size="sm" fw={600}>{name}</Text>
      {detail ? <Text size="xs" c="dimmed">{detail}</Text> : null}
    </Paper>
  );
}

// Shared confirmation for destructive or important actions (#57).
// Closes with Cancel, Escape or ×; never on outside click. While onConfirm runs,
// every way out is locked and the dialog stays open until the result is known.
export function ConfirmDialog({
  opened,
  title,
  message,
  children,
  note,
  item,
  typed,
  tone = "danger",
  actionLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onClose,
  onCancel,
  onBack,
  failureNote = "",
  busy = false,
  confirmDisabled = false,
  size = 480,
}) {
  const [typedValue, setTypedValue] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const runningRef = useRef(false);

  useEffect(() => {
    if (opened) {
      setTypedValue("");
      setError(null);
    }
  }, [opened]);

  const locked = busy || running;
  const matched = !typed || typedValue === typed;
  const canConfirm = matched && !confirmDisabled && !locked && !error?.unknownOutcome;
  const close = () => { if (!locked) onClose?.(); };
  const cancel = () => { if (!locked) (onCancel || onClose)?.(); };

  const submit = async (event) => {
    event?.preventDefault();
    if (!canConfirm || runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setError(null);
    try {
      await onConfirm?.();
    } catch (failure) {
      setError({
        message: failure?.message || "Something went wrong.",
        unknownOutcome: failure?.code === "request_timeout",
      });
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  return (
    <Modal
      opened={opened}
      onClose={close}
      title={<Text fw={700} size="lg">{title}</Text>}
      centered
      size={size}
      closeOnClickOutside={false}
      closeOnEscape={!locked}
      closeButtonProps={{ disabled: locked, "aria-label": "Close" }}
      returnFocus
      data-confirm-tone={tone}
    >
      <form onSubmit={submit} noValidate>
        <Stack gap="md">
          {message ? <Text size="md">{message}</Text> : null}
          {item ? <ConfirmItem {...item} /> : null}
          {note ? <ConfirmNote tone={note.tone}>{note.text}</ConfirmNote> : null}
          {children}
          {typed ? (
            <TextInput
              label={`Type ${typed} to confirm`}
              value={typedValue}
              onChange={(event) => setTypedValue(event.currentTarget.value)}
              disabled={locked}
              autoComplete="off"
              spellCheck={false}
              data-autofocus
            />
          ) : null}
          {error ? (
            <Alert color="red" icon={<IconX size={18} />} title={`Couldn't ${String(actionLabel || "finish").toLowerCase()}.${!error.unknownOutcome && failureNote ? ` ${failureNote}` : ""}`} role="alert">
              {error.message}
              {error.unknownOutcome ? " The result is unknown; refresh to check before trying again." : ""}
            </Alert>
          ) : null}
          <Group justify="space-between" mt={4} wrap="nowrap">
            {onBack ? (
              <Button type="button" variant="subtle" color="gray" leftSection={<IconChevronLeft size={16} />} disabled={locked} onClick={onBack}>
                Back
              </Button>
            ) : <span />}
            <Group gap="sm" wrap="nowrap">
              <Button type="button" variant="default" disabled={locked} onClick={cancel} data-autofocus={typed ? undefined : true}>
                {cancelLabel}
              </Button>
              <Button type="submit" color={CONFIRM_TONE_COLORS[tone] || "red"} loading={locked} disabled={!matched || confirmDisabled || Boolean(error?.unknownOutcome)}>
                {error ? "Try again" : actionLabel}
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
