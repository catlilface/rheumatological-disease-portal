import './home.css'
import { portalTitle } from '../../../shared/config/portal'

export default function HomePage() {
  return (
    <section className="hero">
      <p className="hero__status">Сайт находится в разработке</p>
      <h1>{portalTitle}</h1>
      <p className="hero__intro">
        Скоро здесь появится система, которая поможет вовремя заметить признаки
        ревматологических заболеваний и подскажет, к какому врачу обратиться.
      </p>
      <a className="primary-link" href="/documents">
        Документы портала
      </a>
    </section>
  )
}
