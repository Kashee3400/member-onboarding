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

export type Page<T> = {
  next: string | null;
  previous: string | null;
  results: T[];
};

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

export type Plant = {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
};
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
/** Someone works a colleague's MCCs for some days. `mccs` is what the person away holds now. */
export type MccCover = {
  id: string;
  absent: string;
  absent_name: string;
  colleague: string;
  colleague_name: string;
  starts_on: string;
  ends_on: string;
  reason: string;
  state: "upcoming" | "active" | "over" | "ended";
  mccs: string[];
  given_by_name: string;
  created_at: string;
  ended_at: string | null;
  ended_by_name: string | null;
};
export type NotificationPreference = { morning_summary: boolean };
/** Where an MPP is, keyed as the form's address fields. Empty means the masters don't know it yet. */
export type MppPlace = {
  pooling_point_code: string;
  village_name: string;
  village_code: string;
  hamlet_name: string;
  hamlet_code: string;
  post_office: string;
  tehsil: string;
  tehsil_code: string;
  district: string;
  district_code: string;
  state: string;
  state_code: string;
  pincode: string;
};
export type Mpp = Plant & {
  mcc: string;
  route: string | null;
  village: string | null;
  hamlet: string | null;
  village_code: string;
  village_name: string;
  state_code: string;
  hamlet_code: string;
  source_code: string;
  post_office: string;
  pincode: string;
  place: MppPlace;
};

/** One level of the address chain: state, district, tehsil, village or hamlet. */
export type PlaceMaster = Plant & { name_hi: string; parent_label?: string };
export type StateMaster = PlaceMaster;
export type District = PlaceMaster & { state: string };
export type Tehsil = PlaceMaster & { district: string };
export type Village = PlaceMaster & { tehsil: string };
export type Hamlet = PlaceMaster & { village: string };

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
  /** This person may take the approval back: the form has not moved on since. */
  can_withdraw: boolean;
  approved_by_name: string;
  approved_at: string | null;
  /** The checklist to tick before approving. Empty: the step has none. */
  checks: string[];
  /** What this person has ticked so far, on this submission. */
  ticked: string[];
  /** The checks the approver ticked, as worded then. */
  approved_checks: string[];
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
  /** The reviewer's reason for each marked field, where one was given. */
  rejected_field_notes: Record<string, string>;
  computed: {
    total_animals: number;
    total_in_milk: number;
    surplus_lpd: number;
  };
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
    hamlet_name: string;
    hamlet_code: string;
    post_office: string;
    tehsil: string;
    district: string;
    state: string;
    pincode: string;
  };
  /** Address fields the MPP fills and locks, by field key. */
  mpp_place: Record<string, string>;
  review_steps: ReviewStep[];
  /** When the mobile number and email were confirmed by OTP, or null. */
  contact_verified: { mobile: string | null; email: string | null };
  warnings: string[];
  /** The same warnings by the field they concern, as "section.field". */
  field_warnings: Record<string, string>;
  tr_code: string | null;
  decisions: {
    id: string;
    revision: number;
    stage: string;
    decision: string;
    reason: string;
    rejected_fields: string[];
    field_notes: Record<string, string>;
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
      options?: FormChoice[];
      /** Retired choices: no longer offered, but older forms may still hold them. */
      retired_options?: FormChoice[];
      option_list?: string;
      /** Filled from the MPP by the server, never typed. */
      locked?: boolean;
    }[];
  }[];
  family?: {
    max_members: number;
    genders: FormChoice[];
    relations: FormChoice[];
    retired_genders?: FormChoice[];
    retired_relations?: FormChoice[];
  };
};

export type FormChoice = { value: string; label: string; label_hi?: string };

/** One of the form's dropdown lists, as an administrator edits it. */
export type FormList = {
  key: string;
  title: string;
  description: string;
  options: {
    value: string;
    label: string;
    label_hi: string;
    active: boolean;
  }[];
};

export type BankBranch = {
  id: string;
  ifsc: string;
  bank_name: string;
  branch_name: string;
  address: string;
  district: string;
  is_active: boolean;
  bank_is_active: boolean;
  updated_at: string;
};

export type BankImportResult = {
  created: number;
  updated: number;
  skipped: number;
  repeated: number;
  problems: { row: number; problem: string }[];
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

export type Dashboard = {
  by_status: Record<string, number>;
  waiting_for_me: number;
};

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
  members?: {
    joined_month: number;
    joined_total: number;
    existing_active: number;
  };
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

export type ReportSummary = {
  total: number;
  by_status: Record<string, number>;
};

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
  rows: {
    id: string;
    form_number: string;
    full_name: string;
    tr_code: string;
    mpp: string;
    approved_at: string;
  }[];
};

export type MppPreviewEntry = {
  code: string;
  name: string;
  changes?: Record<string, [string, string]>;
};

export type MppImportPreview = {
  new: MppPreviewEntry[];
  new_count: number;
  changed: MppPreviewEntry[];
  changed_count: number;
  unchanged_count: number;
  missing: MppPreviewEntry[];
  missing_count: number;
  new_plants: number;
  new_mccs: number;
  new_bmcs: number;
  new_routes: number;
};

export type MppImportResult = {
  created: number;
  updated: number;
  problems: { row: number; problem: string }[];
  preview?: MppImportPreview;
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
  draft_retention_days: number;
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

/** A field a reviewer marked wrong on the current submission, kept until the form is decided. */
export type FieldMark = {
  id: string;
  path: string;
  label: string;
  reason: string;
  marked_by_name: string;
  marked_at: string;
  mine: boolean;
  can_remove: boolean;
};

export type ReviewSettings = {
  overdue_days: number;
  reject_reasons: RejectReason[];
  sections: {
    key: string;
    title: string;
    step: string;
    fields: { path: string; label: string }[];
  }[];
  /** Each step's checklist, by step key. */
  checks: Record<string, string[]>;
  steps: { key: string; number: number; title: string }[];
};

export type ConsoleOrganization = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  health: {
    forms_total: number;
    forms_this_week: number;
    pending: number;
    late: number;
    sent_back: number;
    members: number;
    staff: number;
    last_activity: string | null;
    failures_this_week: { mail: number; sms: number; push: number };
    storage_bytes: number;
    storage_limit_mb: number | null;
    setup: {
      branding: boolean;
      email_domain: boolean;
      mail: boolean;
      sms: boolean;
      push: boolean;
      review_steps: boolean;
      signatories: number;
      connected_apps: number;
      mpps: number;
    };
  };
};
