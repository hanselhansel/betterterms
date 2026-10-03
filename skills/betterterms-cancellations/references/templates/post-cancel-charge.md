# Charge after a confirmed cancellation

Use when a charge posts after the provider confirmed the
cancellation in writing. Write to the provider first; a card
`dispute` is a separate step that always needs the user's explicit
yes. Action: `send`. When the provider stated the charge amount,
`{quote:n}` can name it.

```
Hello,

My service was cancelled and you confirmed it in writing. A charge
posted to my card after that confirmation. Please reverse the
charge and confirm the reversal in writing.

Thank you.
```
