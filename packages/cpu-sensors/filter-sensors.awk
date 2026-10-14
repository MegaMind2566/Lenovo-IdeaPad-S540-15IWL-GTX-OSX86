# Only numeric telemetry and fixed diagnostic categories leave this filter.
# Sample headers are recognized, but their dates and other payload are dropped.
function begin_sample() {
    sample++; active=1; labels=0; valid=0; rejected=0; unavailable=0;
    print ""; print "Sample: " sample;
}
function finish_sample(    missing,duplicates,status) {
    if (!active) return;
    missing=(labels==0); duplicates=(labels>1 ? labels-1 : 0);
    if (missing) { status="missing"; missing_samples++; }
    else if (duplicates) { status="duplicate"; duplicate_samples++; }
    else if (valid==1 && rejected==0) { status="valid"; valid_samples++; }
    else { status="rejected"; rejected_samples++; }
    print "CPU temperature status: " status;
    print "Temperature counts: valid values: " valid "; missing line: " missing "; rejected values: " rejected "; duplicate lines: " duplicates;
    print "Unavailable SMC keys reported: " unavailable;
    total_unavailable+=unavailable; total_valid+=valid; total_rejected+=rejected;
    active=0;
}
function temperature(line,    value,unit,fields,count,normal) {
    labels++;
    if (line !~ /^CPU die temperature:/) {
        rejected++; print "CPU temperature diagnostic: unrecognized label format; payload omitted"; return;
    }
    sub(/^CPU die temperature:[ \t]*/, "", line);
    count=split(line,fields,/[ \t]+/);
    if (count!=2 || length(fields[1])>64 || (fields[2]!="C" && fields[2]!="Celsius" && fields[2]!="degC" && fields[2]!="\302\260C")) {
        rejected++; print "CPU temperature diagnostic: unrecognized format; payload omitted"; return;
    }
    value=fields[1]; unit=fields[2]; normal=tolower(value);
    if (value ~ /^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$/) {
        if (value+0>0 && value+0<=110) {
            valid++; print "CPU temperature diagnostic: numeric; value: " value "; unit: " unit "; accepted: yes";
        } else {
            rejected++; print "CPU temperature diagnostic: numeric; value: " value "; unit: " unit "; accepted: no";
        }
        return;
    }
    if (normal=="nan" || normal=="n/a" || normal=="inf" || normal=="+inf" || normal=="-inf") {
        rejected++; print "CPU temperature diagnostic: nonfinite or unavailable; token: " normal "; unit: " unit; return;
    }
    rejected++; print "CPU temperature diagnostic: unrecognized value; payload omitted";
}
{
    sub(/^[ \t]+/, ""); sub(/[ \t\r]+$/, "");
    if ($0 ~ /^\*\*\* Sampled system activity / || $0 ~ /^\*\*\*\* Sampled system activity /) {
        finish_sample(); begin_sample(); next;
    }
    if ($0=="Invalid key detected!") {
        if (active) unavailable++; else startup_unavailable++;
        next;
    }
    if (tolower($0) ~ /^cpu die temperature([ \t]*[:=]|[ \t])/) {
        if (!active) { startup_temperature++; next; }
        temperature($0); next;
    }
    if (!active || length($0)>512) next;
    if ($0 ~ /^Intel energy model derived package power [(]CPUs[+]GT[+]SA[)]: [0-9]+([.][0-9]+)?[ ]?W$/ ||
        $0 ~ /^(System|CPU) Average frequency as fraction of nominal: [0-9]+([.][0-9]+)?% [(][0-9]+([.][0-9]+)? [Mm][Hh][Zz][)]$/ ||
        $0 ~ /^(CPU|IO|GPU) Thermal level: [0-9]+$/ ||
        $0 ~ /^(CPU|GPU) Plimit: [0-9]+([.][0-9]+)?$/ ||
        $0 ~ /^Number of prochots: [0-9]+$/ ||
        $0 ~ /^(Current pressure level|Thermal pressure): (Nominal|Moderate|Heavy|Trapping|Fair|Serious|Critical)$/ ||
        $0 ~ /^Fan: [0-9]+([.][0-9]+)?[ ]?(rpm|RPM)$/) print;
}
END {
    finish_sample();
    print ""; print "Samples observed: " sample+0;
    print "Samples with one valid CPU temperature: " valid_samples+0;
    print "Samples with no CPU temperature line: " missing_samples+0;
    print "Samples with a rejected CPU temperature: " rejected_samples+0;
    print "Samples with duplicate CPU temperature lines: " duplicate_samples+0;
    print "Total valid temperature values: " total_valid+0;
    print "Total rejected temperature values: " total_rejected+0;
    print "Total unavailable SMC keys within samples: " total_unavailable+0;
    print "Unavailable SMC keys before first sample: " startup_unavailable+0;
    print "CPU temperature lines before first sample: " startup_temperature+0;
    if (!sample) print "No recognized sample headers: sample completeness cannot be assessed.";
}
