{{/*
tobogganing.digestGuard: fail the render when image.requireDigest is set and the
digest is missing, not sha256:<64 hex>, or an all-zero placeholder.
Call with: (dict "image" .Values.image "name" "<label>").
*/}}
{{- define "tobogganing.digestGuard" -}}
{{- if .image.requireDigest -}}
{{- $d := required (printf "%s image.digest is required (sha256:<64 hex>) when requireDigest=true - no published digest is pinned" .name) .image.digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $d) -}}
{{- fail (printf "%s image.digest must be sha256:<64 hex>" .name) -}}
{{- end -}}
{{- if regexMatch "^sha256:0{64}$" $d -}}
{{- fail (printf "%s image.digest is an all-zero placeholder - set the real published digest" .name) -}}
{{- end -}}
{{- end -}}
{{- end -}}
