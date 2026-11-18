import './documents.css'
import { policyLinks } from '../../../entities/policy'

export default function DocumentsPage() {
  return (
    <article className="article">
      <h1>Документы портала</h1>
      <ul className="document-list">
        {policyLinks.map(({ title, description, href }) => (
          <li key={href}>
            <div>
              <a href={href}>{title}</a>
              <p>{description}</p>
            </div>
            <span>PDF</span>
          </li>
        ))}
        <li>
          <div>
            <a href="/about">Сведения об операторе</a>
            <p>
              Реквизиты владельца сайта и сведения об организации обработки
              персональных данных.
            </p>
          </div>
        </li>
      </ul>
    </article>
  )
}
