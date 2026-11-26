import type { Article, Material, Survey } from '../src/shared/api/contracts.ts'

export const survey: Survey = {
  survey_id: 'rheuma_screening_v1',
  weights_version: 'draft-v1',
  disclaimer_version: 'demo-v1',
  disclaimer: 'Демонстрационный скрининг с тестовыми весами.',
  confirmation_text: 'Я понимаю, что это не медицинская услуга и не диагноз',
  urgent_notice: 'Обнаружен тестовый красный флаг.',
  thresholds_status: 'draft',
  blocks: [
    {
      code: 'A',
      title: 'Демонстрационные вопросы',
      red_flag: false,
      interrupt: false,
      questions: [
        {
          code: 'A1',
          text: 'Тестовый признак?',
          required: true,
          red_flag: false,
          type: 'boolean',
          weights: { yes: 1, no: 0 },
        },
        {
          code: 'A2',
          text: 'Тестовый вариант',
          required: true,
          red_flag: false,
          type: 'single_choice',
          options: [
            { value: 'first', label: 'Первый', weight: 0 },
            { value: 'second', label: 'Второй', weight: 1 },
          ],
        },
      ],
    },
    {
      code: 'D',
      title: 'Красные флаги',
      red_flag: true,
      interrupt: true,
      questions: [
        {
          code: 'D1',
          text: 'Тестовый красный флаг?',
          required: true,
          red_flag: true,
          type: 'boolean',
        },
      ],
    },
  ],
  scoring: {
    sum_blocks: ['A'],
    thresholds: { low: [0, 1], medium: [2, 2], high: [3, null] },
    red_flag_overrides: true,
  },
}

const material = {
  version: 1,
  reviewer: { display_name: 'Демонстрационный рецензент' },
  published_at: '2026-01-01T00:00:00Z',
  sources: [
    { title: 'Демонстрационный источник', url: 'https://example.org/' },
  ],
}

export const doctorRoute: Material = {
  ...material,
  title: 'Подготовка к приёму',
  body_markdown: 'Демонстрационный материал о подготовке к приёму.',
}

export const article: Article = {
  ...material,
  title: 'Демонстрационная статья',
  section: 'diseases',
  slug: 'demo-article',
  summary: 'Материал для проверки библиотеки.',
  template_version: 'demo-v1',
  body_markdown: 'Текст демонстрационной статьи.',
}
