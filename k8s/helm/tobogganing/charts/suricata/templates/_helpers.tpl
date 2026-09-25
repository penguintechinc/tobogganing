{{/*
Suricata sub-chart naming/label helpers. Self-contained — subcharts render
independently of the parent chart's templates/_helpers.tpl.
*/}}
{{- define "suricata.fullname" -}}
{{- printf "%s-suricata" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "suricata.labels" -}}
app.kubernetes.io/name: suricata
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: tobogganing
app.kubernetes.io/component: sase-adapter-tool
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end }}

{{- define "suricata.selectorLabels" -}}
app.kubernetes.io/name: suricata
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
