import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder } from '@angular/forms';
import { MatSlideToggleChange } from '@angular/material/slide-toggle';
import { Subject } from 'rxjs';

import { ChargeControl, ChargeControlService } from './charge-control.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, OnDestroy {
  private unsubscribe: Subject<void> = new Subject();

  formGroup = this.fb.group({
    phases: [0],
    onePhaseSelector: [false]
  });

  constructor(private fb: FormBuilder, private chargeControlService: ChargeControlService) {}

  ngOnInit(): void {
    this.refresh();
  }

  ngOnDestroy(): void {
    this.unsubscribe.next();
    this.unsubscribe.complete();
  }

  refresh(): void {
    this.chargeControlService.getChargeControl().subscribe(cc => {
      // console.log(`Refresh: phases = ${cc.phases}`);
      this.formGroup.patchValue(cc);
      this.formGroup.get('onePhaseSelector')?.setValue(cc.phases === 1);
    });
  }

  onPhaseChange(event: MatSlideToggleChange): void {
    const phases = event.checked ? 1 : 3;
    // console.log(`onPhaseChange = ${phases}`);
    this.chargeControlService.putChargeControlPhases(phases).subscribe(
      () => this.refresh()
    );
  }
}
