import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepProgress, TypingIndicator } from './StepProgress'
import { PLANNING_STEPS, STEP_LABELS } from '@/types/api'

describe('StepProgress', () => {
  it('renders every planning step label', () => {
    render(<StepProgress completedSteps={[]} done={false} />)
    for (const step of PLANNING_STEPS) {
      expect(screen.getByText(STEP_LABELS[step])).toBeInTheDocument()
    }
  })

  it('strikes through completed steps', () => {
    render(<StepProgress completedSteps={['parse_preferences']} done={false} />)
    expect(screen.getByText(STEP_LABELS.parse_preferences).className).toContain('line-through')
  })

  it('does not strike through steps that have not completed yet', () => {
    render(<StepProgress completedSteps={['parse_preferences']} done={false} />)
    expect(screen.getByText(STEP_LABELS.search_flights).className).not.toContain('line-through')
  })

  it('highlights the first not-yet-completed step as current', () => {
    render(<StepProgress completedSteps={['parse_preferences']} done={false} />)
    expect(screen.getByText(STEP_LABELS.search_flights).className).toContain('font-medium')
  })

  it('no step is marked current once done', () => {
    render(<StepProgress completedSteps={['parse_preferences']} done={true} />)
    expect(screen.getByText(STEP_LABELS.search_flights).className).not.toContain('font-medium')
  })
})

describe('TypingIndicator', () => {
  it('renders a status role', () => {
    render(<TypingIndicator />)
    expect(screen.getByRole('status', { name: 'Agent is typing' })).toBeInTheDocument()
  })
})
