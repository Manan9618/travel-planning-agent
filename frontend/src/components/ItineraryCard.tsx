import { useState } from 'react'
import type { BudgetEvaluation, DayPlan, Itinerary } from '@/types/api'
import { dayColor } from '@/lib/dayColors'
import { MapPreview } from '@/components/MapPreview'

interface Props {
  itinerary: Itinerary
  budgetEvaluation: BudgetEvaluation | null
  onDownloadPdf: () => void
  onOpenMap: () => void
  pdfAvailable: boolean
  mapAvailable: boolean
}

function DayRow({ day }: { day: DayPlan }) {
  const [expanded, setExpanded] = useState(day.day_number <= 2)
  const color = dayColor(day.day_number)

  return (
    <div className="border-b border-gray-200 last:border-b-0 dark:border-gray-700">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
        aria-expanded={expanded}
      >
        <span
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ backgroundColor: color }}
        >
          {day.day_number}
        </span>
        <span className="flex-1 font-medium text-gray-900 dark:text-gray-100">
          Day {day.day_number} &middot;{' '}
          {new Date(day.date).toLocaleDateString(undefined, {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
          })}
        </span>
        <span className="text-gray-400 transition-transform" aria-hidden>
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {day.items.length === 0 ? (
            <p className="text-sm italic text-gray-500 dark:text-gray-400">
              Free day &mdash; nothing scheduled
            </p>
          ) : (
            <ul className="space-y-1.5">
              {day.items.map((item, i) => (
                <li key={i} className="flex items-baseline gap-3 text-sm">
                  <span className="w-12 shrink-0 tabular-nums text-gray-500 dark:text-gray-400">
                    {item.start_time.slice(11, 16)}
                  </span>
                  <span className="flex-1 text-gray-800 dark:text-gray-200">{item.title}</span>
                  <span className="shrink-0 text-xs text-gray-400">{item.activity_type}</span>
                  {item.cost != null && (
                    <span className="shrink-0 text-xs font-medium text-gray-600 dark:text-gray-300">
                      ${item.cost.toFixed(0)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {day.warnings.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {day.warnings.map((w, i) => (
                <li key={i} className="text-xs text-amber-600 dark:text-amber-400">
                  {w}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function BudgetTable({ evaluation }: { evaluation: BudgetEvaluation }) {
  const statusColor: Record<string, string> = {
    under: 'text-green-600 dark:text-green-400',
    over: 'text-red-600 dark:text-red-400 font-semibold',
    on_target: 'text-gray-600 dark:text-gray-300',
  }
  return (
    <div className="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
      <h3 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">Budget</h3>
      <table className="w-full text-sm">
        <tbody>
          {evaluation.categories.map((cat) => (
            <tr key={cat.category} className="border-b border-gray-100 last:border-b-0 dark:border-gray-800">
              <td className="py-1 capitalize text-gray-700 dark:text-gray-300">{cat.category}</td>
              <td className="py-1 text-right tabular-nums text-gray-500 dark:text-gray-400">
                ${cat.allocated.toFixed(0)}
              </td>
              <td className="py-1 text-right tabular-nums text-gray-700 dark:text-gray-200">
                ${cat.actual.toFixed(0)}
              </td>
              <td className={`py-1 pl-2 text-right capitalize ${statusColor[cat.status]}`}>
                {cat.status.replace('_', ' ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {evaluation.adherence_score != null && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          Budget adherence: <b>{(evaluation.adherence_score * 100).toFixed(0)}%</b>
        </p>
      )}
    </div>
  )
}

export function ItineraryCard({
  itinerary,
  budgetEvaluation,
  onDownloadPdf,
  onOpenMap,
  pdfAvailable,
  mapAvailable,
}: Props) {
  return (
    <div className="w-full max-w-xl overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-700">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">
            {itinerary.preferences.destination}
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {itinerary.days.length} day{itinerary.days.length !== 1 ? 's' : ''}
            {itinerary.preferences.budget_total
              ? ` · $${itinerary.preferences.budget_total.toLocaleString()} budget`
              : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onOpenMap}
            disabled={!mapAvailable}
            className="rounded-md border border-gray-300 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            Full map
          </button>
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={!pdfAvailable}
            className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Download PDF
          </button>
        </div>
      </div>

      <div className="p-3">
        <MapPreview itinerary={itinerary} />
      </div>

      <div>
        {itinerary.days.map((day) => (
          <DayRow key={day.day_number} day={day} />
        ))}
      </div>

      {budgetEvaluation && <BudgetTable evaluation={budgetEvaluation} />}
    </div>
  )
}
