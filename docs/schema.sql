PRAGMA foreign_keys = ON;

CREATE TABLE Product (
  product_id TEXT PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  category_l1 TEXT NOT NULL,
  category_l2 TEXT NOT NULL,
  list_price NUMERIC NOT NULL CHECK (list_price > 0),
  unit_cost NUMERIC NOT NULL CHECK (unit_cost >= 0),
  launch_date TEXT NOT NULL,
  discontinued_date TEXT
);

CREATE TABLE Customer (
  customer_id TEXT PRIMARY KEY,
  signup_date TEXT NOT NULL,
  country TEXT NOT NULL,
  region TEXT NOT NULL,
  age_band TEXT NOT NULL,
  acquisition_channel TEXT NOT NULL,
  preferred_channel TEXT NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('STANDARD','PLUS','PREMIUM')),
  lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('NEW','ACTIVE','DORMANT','CHURNED','SUPPRESSED')),
  synthetic_email_token TEXT NOT NULL UNIQUE,
  is_test_account INTEGER NOT NULL CHECK (is_test_account IN (0,1))
);

CREATE TABLE SegmentRule (
  segment_id TEXT PRIMARY KEY,
  segment_name TEXT NOT NULL UNIQUE,
  exclusive_group TEXT,
  priority INTEGER NOT NULL,
  rule_expression TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT
);

CREATE TABLE ActionCatalog (
  action_code TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('MARKETING','SERVICE')),
  cooldown_days INTEGER NOT NULL CHECK (cooldown_days >= 0),
  unit_cost NUMERIC NOT NULL CHECK (unit_cost >= 0),
  requires_consent_channel TEXT,
  active_flag INTEGER NOT NULL CHECK (active_flag IN (0,1))
);

CREATE TABLE OrderHeader (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  order_ts TEXT NOT NULL,
  order_type TEXT NOT NULL CHECK (order_type IN ('SALE','RETURN')),
  status TEXT NOT NULL,
  currency TEXT NOT NULL,
  gross_amount NUMERIC NOT NULL CHECK (gross_amount >= 0),
  discount_amount NUMERIC NOT NULL CHECK (discount_amount >= 0),
  net_amount NUMERIC NOT NULL CHECK (net_amount >= 0),
  related_order_id TEXT REFERENCES OrderHeader(order_id)
);

CREATE TABLE OrderLine (
  order_line_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES OrderHeader(order_id),
  product_id TEXT NOT NULL REFERENCES Product(product_id),
  quantity INTEGER NOT NULL CHECK (quantity >= 1),
  unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
  discount NUMERIC NOT NULL CHECK (discount >= 0),
  line_total NUMERIC NOT NULL CHECK (line_total >= 0),
  line_type TEXT NOT NULL CHECK (line_type IN ('SALE','RETURN')),
  original_order_line_id TEXT REFERENCES OrderLine(order_line_id)
);

CREATE TABLE EngagementEvent (
  event_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  action_id TEXT,
  product_id TEXT REFERENCES Product(product_id),
  event_type TEXT NOT NULL,
  channel TEXT NOT NULL,
  event_ts TEXT NOT NULL,
  parent_event_id TEXT REFERENCES EngagementEvent(event_id)
);

CREATE TABLE SupportCase (
  case_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  order_id TEXT REFERENCES OrderHeader(order_id),
  severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  status TEXT NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED','REOPENED')),
  opened_at TEXT NOT NULL,
  resolved_at TEXT,
  closed_at TEXT,
  handle_minutes INTEGER NOT NULL CHECK (handle_minutes >= 0),
  cost_amount NUMERIC NOT NULL CHECK (cost_amount >= 0),
  csat INTEGER CHECK (csat IS NULL OR csat BETWEEN 1 AND 5)
);

CREATE TABLE Consent (
  consent_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  channel TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','PUSH','PHONE')),
  purpose TEXT NOT NULL CHECK (purpose IN ('MARKETING','SERVICE')),
  status TEXT NOT NULL CHECK (status IN ('GRANTED','WITHDRAWN')),
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  source TEXT NOT NULL
);

CREATE TABLE SegmentMembership (
  membership_id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL REFERENCES SegmentRule(segment_id),
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  recency_days INTEGER,
  frequency_12m INTEGER,
  monetary_net_12m NUMERIC,
  r_score INTEGER,
  f_score INTEGER,
  m_score INTEGER,
  rule_matched TEXT NOT NULL,
  evidence TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','EXITED'))
);

CREATE TABLE SegmentMembershipSnapshot (
  snapshot_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  segment_id TEXT NOT NULL REFERENCES SegmentRule(segment_id),
  snapshot_date TEXT NOT NULL,
  recency_days INTEGER NOT NULL,
  frequency_12m INTEGER NOT NULL,
  monetary_net_12m NUMERIC NOT NULL,
  rule_matched TEXT NOT NULL,
  evidence TEXT NOT NULL
);

CREATE TABLE ActionOutcome (
  action_outcome_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  action_code TEXT NOT NULL REFERENCES ActionCatalog(action_code),
  segment_id TEXT REFERENCES SegmentRule(segment_id),
  membership_id TEXT REFERENCES SegmentMembership(membership_id),
  recommended_at TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('RECOMMENDED','SUPPRESSED','SENT')),
  suppression_reason TEXT,
  sent_at TEXT,
  outcome TEXT NOT NULL CHECK (outcome IN ('NONE','OPENED','CLICKED','CONVERTED','UNSUBSCRIBED')),
  outcome_at TEXT,
  attributed_order_id TEXT REFERENCES OrderHeader(order_id),
  attribution_window_days INTEGER,
  control_group_flag INTEGER NOT NULL CHECK (control_group_flag IN (0,1))
);

CREATE TABLE SegmentMembershipEvent (
  membership_event_id TEXT PRIMARY KEY,
  membership_id TEXT NOT NULL REFERENCES SegmentMembership(membership_id),
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  segment_id TEXT NOT NULL REFERENCES SegmentRule(segment_id),
  event_type TEXT NOT NULL CHECK (event_type IN ('ENTER','EXIT')),
  event_ts TEXT NOT NULL
);

CREATE TABLE CustomerStatusEvent (
  status_event_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  old_status TEXT,
  new_status TEXT NOT NULL,
  event_ts TEXT NOT NULL
);

CREATE TABLE ConsentEvent (
  consent_event_id TEXT PRIMARY KEY,
  consent_id TEXT NOT NULL REFERENCES Consent(consent_id),
  customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
  event_type TEXT NOT NULL CHECK (event_type IN ('GRANTED','WITHDRAWN')),
  event_ts TEXT NOT NULL
);

CREATE TABLE ActionEligibilityBridge (
  action_code TEXT NOT NULL REFERENCES ActionCatalog(action_code),
  segment_id TEXT NOT NULL REFERENCES SegmentRule(segment_id),
  effective_from TEXT NOT NULL,
  effective_to TEXT,
  PRIMARY KEY (action_code, segment_id, effective_from)
);
