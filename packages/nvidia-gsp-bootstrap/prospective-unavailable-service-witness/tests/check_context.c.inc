/* SPDX-License-Identifier: MIT; actual inserted post-wrapper C helper. */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "S540HostUnavailableDiagnostics.h"
enum { NV_DBG_ERRORS=1 };
typedef struct S540GspContext { unsigned nv; } S540GspContext;
static S540GspContext context;
static S540HostUnavailableDiagnostics sample;
static NV_STATUS wantedStatus;
static unsigned checks,failures,calls,reads;
static char logBuffer[4096];
#define EXPECT(v) do{++checks;if(!(v)){++failures;fprintf(stderr,"Context control line %d\n",__LINE__);}}while(0)
NV_STATUS s540GlobalRmReadUnavailableDiagnostics(const void *nv,S540HostUnavailableDiagnostics *out) {
    EXPECT(nv==&context.nv);++reads;
    if(wantedStatus!=NV_OK)return wantedStatus;
    *out=sample;return NV_OK;
}
static int nv_printf(unsigned level,const char *format,...) {
    EXPECT(level==NV_DBG_ERRORS);++calls;va_list args;va_start(args,format);
    int result=vsnprintf(logBuffer+strlen(logBuffer),sizeof(logBuffer)-strlen(logBuffer),format,args);
    va_end(args);return result;
}
#include "actual-context.inc"
int main(void) {
    sample.format=1;sample.bytes=sizeof(sample);sample.observedMask=3;
    sample.unavailableCallsLifetime=37;sample.sitesObservedMask=0x3ff;sample.firstState=2;
    sample.firstSite=4;sample.firstService=18;
    for(unsigned i=0;i<10;++i)sample.siteCallsLifetime[i]=101+i;
    s540LogUnavailableServiceWitness(&context);
    EXPECT(calls==2 && reads==1);
    EXPECT(strstr(logBuffer,"scope=module-lifetime independentlySampled=1"));
    EXPECT(strstr(logBuffer,"total=37 siteMask=0x3ff firstState=2 firstObserved=1 firstSite=4 firstService=18"));
    EXPECT(strstr(logBuffer,"externalSiteAmbiguous=1"));
    EXPECT(strstr(logBuffer,"external=101 shutdownOrdinary=102 allocationOrdinary=103 freeOrdinary=104 freePermit=105 freeCompletion=106 snapshotOrdinary=107 serviceRange=108 nullServiceName=109 serviceTableFull=110"));
    calls=reads=0;logBuffer[0]=0;sample.observedMask=1;sample.firstState=1;
    s540LogUnavailableServiceWitness(&context);
    EXPECT(calls==2 && reads==1);
    EXPECT(strstr(logBuffer,"firstObserved=0 firstSite=0 firstService=0"));
    calls=reads=0;logBuffer[0]=0;wantedStatus=NV_ERR_NOT_READY;
    s540LogUnavailableServiceWitness(&context);
    EXPECT(calls==1 && reads==1 && strstr(logBuffer,"available=0 status="));
    EXPECT(!strstr(logBuffer,"S540 unavailable sites:"));
    printf("{\"cases\":3,\"checks\":%u,\"failures\":%u}\n",checks,failures);
    return failures?1:0;
}
