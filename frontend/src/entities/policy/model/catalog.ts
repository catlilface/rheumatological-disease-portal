const policySlugs = [
  'personal-info',
  'personal-info-agreement',
  'user-agreement',
  'medical-advices',
  'ai',
  'account-deletion',
  'cookies',
] as const

type PolicySlug = (typeof policySlugs)[number]

export function policyHref(slug: PolicySlug) {
  return `/policy/${slug}`
}

export const policyLinks = policySlugs.map((slug) => ({
  href: policyHref(slug),
  title: `policy.${slug}.title` as const,
  description: `policy.${slug}.description` as const,
}))
