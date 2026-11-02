export const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "pending_am", label: "Pending Area Manager" },
  { value: "pending_cs", label: "Pending CS & Legal" },
  { value: "pending_finance", label: "Pending Finance" },
  { value: "rejected", label: "Rejected" },
  { value: "approved", label: "Approved" },
];

export const STAGE_PERMISSION: Record<string, string> = {
  pending_am: "applications.approve_am",
  pending_cs: "applications.approve_cs",
  pending_finance: "applications.approve_finance",
};

/** A decision records its stage as the status the form had. */
export const STAGE_LABEL: Record<string, string> = {
  pending_am: "Area Manager",
  pending_cs: "CS & Legal",
  pending_finance: "Finance",
};

export const STAGE_QUEUE: Record<string, string> = {
  pending_am: "/approvals/area-manager",
  pending_cs: "/approvals/cs-legal",
  pending_finance: "/approvals/finance",
};

export const STATUS_ORDER = ["pending_am", "pending_cs", "pending_finance", "approved", "rejected", "draft"];
