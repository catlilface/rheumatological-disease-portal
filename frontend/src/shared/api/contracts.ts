// Browser-facing subset of contracts/http/bff-v1.openapi.yaml and schemas.yaml.
export type AnswerValue = boolean | string
export type Question = {
  code: string
  text: string
  required: boolean
  red_flag: boolean
} & (
  | { type: 'boolean'; weights?: Record<'yes' | 'no', number> }
  | {
      type: 'single_choice'
      options: { value: string; label: string; weight: number }[]
    }
)

type Disclaimer = { disclaimer: string; disclaimer_version: string }
type SurveyRef = { survey_id: string; weights_version: string }
type ThresholdsStatus = 'draft' | 'approved'
export type Survey = SurveyRef &
  Disclaimer & {
    thresholds_status: ThresholdsStatus
    confirmation_text: string
    urgent_notice: string
    blocks: {
      code: string
      title: string
      red_flag: boolean
      interrupt: boolean
      questions: Question[]
    }[]
    scoring: {
      sum_blocks: string[]
      thresholds: Record<'low' | 'medium' | 'high', [number, number | null]>
      red_flag_overrides: true
    }
  }

export type Start = SurveyRef &
  Pick<Disclaimer, 'disclaimer_version'> & { disclaimer_accepted: true }
export type Revision = { expected_session_version: number }
export type Answer = Revision & { question_code: string; value: AnswerValue }
export type ResultRef = { result_id: string; version: number }
export type Screening = SurveyRef &
  Disclaimer & {
    screening_id: string
    version: number
    status: 'in_progress' | 'completed' | 'abandoned'
    interrupted_by_red_flag: boolean
    answers: Omit<Answer, 'expected_session_version'>[]
    result: ResultRef | null
  }

export type Result = SurveyRef &
  Disclaimer &
  ResultRef & {
    screening_id: string
    thresholds_status: ThresholdsStatus
    risk_level: 'low' | 'medium' | 'high' | 'red_flag'
    red_flag: boolean
    red_flag_codes: string[]
    score: number | null
    scoring_complete: boolean
    block_scores: Record<string, number>
    contributing_answers: {
      block_code: string
      question_code: string
      label: string
      value: AnswerValue
      weighted_score: number
    }[]
    recommendations: { code: string; text: string }[]
  }

export type Explanation = {
  result: ResultRef
  mode: 'generated' | 'curated_fallback'
  explanation: string
  questions_for_doctor: string[]
  disclaimer: string
  sources: { slug: string; version: number }[]
}

type Reviewed = {
  title: string
  version: number
  reviewer: { display_name: string }
  published_at: string
}
export type Material = Reviewed & {
  body_markdown: string
  sources: { title: string; url: string }[]
}
type ArticleSummary = Reviewed & {
  slug: string
  section: 'diseases' | 'medications' | 'special_situations'
  summary: string
  disease_tag?: string
}
export type Article = ArticleSummary & Material & { template_version: string }
export type ArticlePage = {
  items: ArticleSummary[]
  total: number
  offset: number
  limit: number
}

export type Principal = {
  kind: 'guest' | 'member' | 'staff'
  roles: string[]
  session_expires_at: string
}
export type Receipt = { operation_id: string; status_url: string }
export type Operation = {
  operation_id: string
  state: 'pending' | 'processing' | 'succeeded' | 'rejected' | 'failed'
  resources: { resource_type: string; resource_id: string; version?: number }[]
  updated_at: string
  error?: { code: string; message: string }
}
