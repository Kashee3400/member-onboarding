"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { FormDialog } from "@/components/admin/form-dialog";
import { Field } from "@/components/common/field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useMe } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import type { ApplicationDetail } from "@/lib/types";

/**
 * The platform operator removes a form outright, so it can be filled again from the
 * start. Nobody else sees this. The reason stays in the audit log.
 */
export function DeleteForm({
  application,
}: {
  application: ApplicationDetail;
}) {
  const me = useMe();
  const router = useRouter();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const remove = useMutation({
    mutationFn: () =>
      api(`console/applications/${application.id}/delete`, {
        method: "POST",
        body: { reason: reason.trim() },
      }),
    onSuccess: () => {
      client.invalidateQueries();
      toast.success("Form deleted. It can be filled again from the start.");
      router.push("/applications");
    },
  });
  if (!me.platform_operator) return null;

  const name = application.form_number || "this draft";
  return (
    <>
      <Button
        variant="ghost"
        className="text-destructive hover:text-destructive"
        onClick={() => setOpen(true)}
      >
        <Trash2 /> Delete form
      </Button>
      {open ? (
        <FormDialog
          title={`Delete ${name}?`}
          description="For a form that must be filled again from the start."
          onClose={() => setOpen(false)}
          onSubmit={(event) => {
            event.preventDefault();
            remove.mutate();
          }}
          error={remove.error}
          footer={
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={remove.isPending || reason.trim().length < 5}
              >
                {remove.isPending ? "Deleting…" : "Delete for good"}
              </Button>
            </>
          }
        >
          <Alert variant="destructive">
            <AlertDescription>
              The form, its photos and printed forms, every approval
              {application.status === "approved"
                ? ", and the member it made"
                : ""}{" "}
              are removed and cannot be brought back. Its Aadhaar number, mobile
              and account become free for a new form.
            </AlertDescription>
          </Alert>
          <Field
            label="Why"
            htmlFor="delete-reason"
            help="Kept in the audit log, with your name."
          >
            <Textarea
              id="delete-reason"
              required
              minLength={5}
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              autoFocus
            />
          </Field>
        </FormDialog>
      ) : null}
    </>
  );
}
