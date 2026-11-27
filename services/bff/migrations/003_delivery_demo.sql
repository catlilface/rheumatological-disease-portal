-- migrate:up
CREATE TABLE public.delivery_demo_counters (
    id uuid PRIMARY KEY,
    value bigint NOT NULL
);

CREATE TABLE public.delivery_demo_projection (
    id uuid PRIMARY KEY,
    value bigint NOT NULL
);

-- migrate:down
DROP TABLE public.delivery_demo_projection;
DROP TABLE public.delivery_demo_counters;
