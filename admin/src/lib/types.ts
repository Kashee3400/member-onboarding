export type NavItem = {
  key: string;
  label: string;
  icon: string;
  path: string | null;
  description?: string;
  children: NavItem[];
};

export type Me = {
  id: string;
  email: string;
  full_name: string;
  organization: { id: string; name: string; slug: string };
  roles: string[];
  role_names?: string[];
  membership_id: string;
  photo_url: string | null;
  /** Their own signature is printed on forms: facilitators, Area Managers and heads. */
  needs_signature: boolean;
  has_signature: boolean;
  permissions: string[];
};

export type Page<T> = { next: string | null; previous: string | null; results: T[] };

export type Role = {
  id: string;
  code: string;
  name: string;
  is_system: boolean;
  requires_mfa: boolean;
  permissions: string[];
};

export type Permission = { code: string; description: string };

export type Staff = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  /** Invited people have not chosen a password yet. */
  status: "active" | "inactive" | "invited";
  needs_signature: boolean;
  has_signature: boolean;
  photo_url: string | null;
  roles: { id: string; code: string; name: string }[];
  created_at: string;
};

export type Plant = { id: string; code: string; name: string; is_active: boolean };
export type Bmc = Plant & { mcc: string };
export type Route = Plant & { bmc: string; mcc: string };
export type Mcc = Plant & {
  plant: string;
  mpp_count: number;
  allotted: { name: string; roles: string[] }[];
};
export type MccAssignment = {
  id: string;
  membership: string;
  person: string;
  roles: string[];
  started_at: string;
  ended_at: string | null;
};
export type Mpp = Plant & { mcc: string; route: string | null; village_code: string; village_name: string; state_code: string; hamlet_code: string; source_code: string };

export type Assignment = {
  id: string;
  membership: string;
  person: string;
  responsibility: "facilitator" | "area_manager";
  started_at: string;
  ended_at: string | null;
};

export type Integration = {
  kind: string;
  is_enabled: boolean;
  config: Record<string, string | number | boolean>;
  configured_secrets: string[];
};

export type AuditEvent = {
  id: string;
  occurred_at: string;
  actor_id: string | null;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string;
  ip_address: string | null;
  metadata: Record<string, unknown>;
};

export type ApplicationSummary = {
  id: string;
  form_number: string;
  status: string;
  status_label: string;
  mpp: string;
  mpp_code: string;
  mpp_name: string;
  applicant_name: string;
  created_by_name: string;
  submitted_at: string | null;
  /** When it reached its current stage. */
  waiting_since: string | null;
  /** Waiting at its stage for longer than the organization allows. */
  is_overdue: boolean;
  /** Set once approved: the member code and the day of final approval. */
  tr_code: string;
  approved_at: string | null;
  updated_at: string;
};

export type ReviewStep = {
  key: string;
  number: number;
  title: string;
  sections: string[];
  documents: string[];
  /** This person acts on the step. Every other step is theirs to read only. */
  mine: boolean;
  can_approve: boolean;
  approved_by_name: string;
  approved_at: string | null;
};

export type ApplicationDetail = ApplicationSummary & {
  version: number;
  revision: number;
  data: Record<string, Record<string, unknown>> & {
    family?: { name: string; gender: string; age: number; relation: string }[];
  };
  payment: {
    bank_name?: string;
    branch_name?: string;
    reference?: string;
    amount?: number;
    deposited_on?: string;
    mode?: string;
    share_quantity?: number;
    bank_address?: string;
    recorded_by_name?: string;
  };
  aadhaar_last4: string;
  account_last4: string;
  rejection_reason: string;
  rejected_fields: string[];
  computed: { total_animals: number; total_in_milk: number; surplus_lpd: number };
  fee: {
    admission_fee: number;
    share_quantity: number;
    share_price: number;
    is_shg_member: boolean | null | undefined;
  };
  place: {
    mcc_code: string;
    mcc_name: string;
    bmc_name: string;
    route_name: string;
    mpp_code: string;
    mpp_name: string;
    village_name: string;
    village_code: string;
    as_on_date: string | null;
    tehsil: string;
    district: string;
  };
  review_steps: ReviewStep[];
  warnings: string[];
  tr_code: string | null;
  decisions: {
    id: string;
    revision: number;
    stage: string;
    decision: string;
    reason: string;
    rejected_fields: string[];
    decided_by_name: string;
    decided_at: string;
  }[];
  /** Newest first. Each keeps what was sent, so a resubmission can be compared. */
  revisions: {
    number: number;
    data: ApplicationDetail["data"];
    aadhaar_last4: string;
    account_last4: string;
    submitted_by_name: string;
    submitted_at: string;
  }[];
};

export type FormSchema = {
  version: number;
  sections: {
    key: string;
    title: string;
    fields: {
      key: string;
      label: string;
      type: string;
      required: boolean;
      options?: { value: string; label: string }[];
    }[];
  }[];
};

export type LegacyMember = {
  id: string;
  tr_code: string;
  full_name: string;
  mpp_code: string;
  mpp_name: string;
  is_active: boolean;
};

export type Member = {
  id: string;
  tr_code: string;
  full_name: string;
  mobile: string;
  mpp_code: string;
  joined_at: string;
};

export type AppNotification = {
  id: string;
  title: string;
  body: string;
  application: string | null;
  read_at: string | null;
  created_at: string;
};

export type TrustedIssuer = {
  id: string;
  name: string;
  issuer: string;
  audience: string;
  public_key: string;
  default_role_code: string;
  syncs_mpp_assignments: boolean;
  is_active: boolean;
};

export type Dashboard = { by_status: Record<string, number>; waiting_for_me: number };

export type BreakdownRow = {
  key: string;
  name: string;
  code: string;
  started: number;
  submitted: number;
  pending: number;
  approved: number;
  rejected: number;
  group_code?: string;
  group_name?: string;
};

/** The home page. Each block is there only for those it is meant for. */
export type Home = {
  by_status: Record<string, number>;
  my_queue?: {
    waiting: number;
    /** Waiting longer than overdue_days at their stage. */
    overdue: number;
    overdue_days: number;
    oldest_days: number | null;
    steps_today: number;
    steps_week: number;
  };
  by_mcc?: { code: string; name: string; waiting: number; overdue: number }[];
  trend?: { day: string; submitted: number; joined: number }[];
  fee?: { payment_missing: number; collected_month: number };
  members?: { joined_month: number; joined_total: number; existing_active: number };
  mine?: { approved_month: number; edited_by_me: number };
  setup?: {
    steps_without_role: number;
    mccs_without_area_manager: number;
    signatures_missing: number;
    signatories_missing: number;
  };
};

export type StatusCounts = { by_status: Record<string, number>; total: number };

export type OpenWork = {
  drafts: {
    id: string;
    status: string;
    applicant_name: string;
    last_edited_by_name: string;
    updated_at: string;
  }[];
};

export type ReportSummary = { total: number; by_status: Record<string, number> };

export type PdfBatch = {
  id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  variant: "full" | "single";
  want_zip: boolean;
  want_merged: boolean;
  label: string;
  form_count: number;
  /** "render" makes each form, "merge" joins them into print files. */
  phase: "render" | "merge";
  /** How far through the forms the current phase is. */
  cursor: number;
  processed: number;
  failed_count: number;
  failed_forms: string[];
  current_form: string;
  merged_parts: { index: number; name: string; forms: number; bytes: number }[];
  error: string;
  queue_position: number | null;
  started_at: string | null;
  finished_at: string | null;
  expires_at: string | null;
  requested_by_name: string;
  created_at: string;
};

export type PrintPreview = {
  count: number;
  limit: number;
  ready: number;
  estimated_seconds: number;
  estimated_bytes: number;
  rows: { id: string; form_number: string; full_name: string; tr_code: string; mpp: string; approved_at: string }[];
};

export type MppImportResult = {
  created: number;
  updated: number;
  problems: { row: number; problem: string }[];
};

export type OrganizationProfile = {
  company_name_hi: string;
  company_name_hi_short: string;
  cin: string;
  address_line_1: string;
  address_line_2: string;
  phone: string;
  website: string;
  email: string;
  city_hi: string;
  city_short_hi: string;
  place: string;
  board_resolution_no: string;
  board_resolution_date: string | null;
  members_female_only: boolean;
};

export type MemberCodeSettings = {
  state_code: string;
  hamlet_code: string;
  form_prefix: string;
  entry_fee: number;
  share_price: number;
  share_count: number;
};

export type ApplicationDocument = {
  id: string;
  document_type: string;
  label: string;
  uploaded_by_name: string;
  created_at: string;
};

/** A ready-made reason for sending a form back, and the fields it marks. */
export type RejectReason = { text: string; section: string; fields: string[] };

export type ReviewSettings = {
  overdue_days: number;
  reject_reasons: RejectReason[];
  sections: { key: string; title: string; step: string; fields: { path: string; label: string }[] }[];
};
