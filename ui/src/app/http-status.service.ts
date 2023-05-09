import { HttpRequest, HttpEvent, HttpErrorResponse, HttpHandlerFn } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { BehaviorSubject, Observable, Subject } from 'rxjs';
import { tap, finalize } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class HttpStatusService {
  private busyCnt = 0;
  private busySubject = new BehaviorSubject<boolean>(false);
  private httpErrorSubject = new Subject<string>();

  incBusy(): void {
    this.busyCnt++;
    if (this.busyCnt === 1) {
      this.busySubject.next(true);
    }
  }

  decBusy(): void {
    this.busyCnt--;
    if (this.busyCnt === 0) {
      this.busySubject.next(false);
    }
  }

  notifyHttpError(msg: string): void {
    this.httpErrorSubject.next(msg);
  }

  busy(): Observable<boolean> {
    return this.busySubject.asObservable();
  }

  httpError(): Observable<string> {
    return this.httpErrorSubject.asObservable();
  }
}

// eslint-disable-next-line  @typescript-eslint/no-explicit-any
export function statusInterceptor(req: HttpRequest<any>, next: HttpHandlerFn): Observable<HttpEvent<any>> {
  const statusService = inject(HttpStatusService);
  statusService.incBusy();

  return next(req).pipe(
    tap({
      next: () => null,
      error: errEvent => {
        let msg: string;
        if (errEvent instanceof HttpErrorResponse) {
          msg = `HTTP ${errEvent.status} ${errEvent.statusText} - ${req.method} ${req.url}`;
        } else {
          msg = `Unknown error - ${req.method} ${req.url}`;
        }
        console.log(`Http request failed: ${msg}`);
        statusService.notifyHttpError(msg);
      }
    }),
    finalize(() => {
      // is also called on canceled requests
      statusService.decBusy();
    })
  );
}
